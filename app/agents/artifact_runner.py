"""Use the application's configured AI providers for structured code artifacts."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from app.agent_instructions import load_agent_section
from app.agents.reqnroll_validation import IncompleteImplementationError
from app.agents.runner import (
    CopilotAgentRunner,
    CopilotGenerationError,
    OutputModel,
    StructuredAgentDefinition,
    json_object,
)
from app.config import Settings
from app.generator import _codex_failure_message, _openai_output_text, _strict_json_schema
from app.services.model_access import clear_provider_exhausted, mark_provider_exhausted
from app.services.usage import codex_output, record_provider_usage
from app.subprocess_cleanup import stop_process_tree

logger = logging.getLogger(__name__)


class ArtifactGenerationRunner:
    def __init__(self, settings: Settings, client_factory: Callable[..., Any] | None = None):
        self.settings = settings
        self.copilot = CopilotAgentRunner(settings, client_factory)

    async def generate_structured(
        self,
        definition: StructuredAgentDefinition[OutputModel],
        *,
        instructions: str,
        prompt: str,
        validate: Callable[[OutputModel], OutputModel] | None = None,
    ) -> OutputModel:
        async def copilot(current_prompt: str) -> OutputModel:
            return await self.copilot.generate_structured(
                definition, instructions=instructions, prompt=current_prompt
            )

        async def openai(current_prompt: str) -> OutputModel:
            return await self._openai(definition, instructions, current_prompt)

        async def codex(current_prompt: str) -> OutputModel:
            return await self._codex(definition, instructions, current_prompt)

        async def gemini(current_prompt: str) -> OutputModel:
            return await self._gemini(definition, instructions, current_prompt)

        providers: list[tuple[str, Callable[[str], Awaitable[OutputModel]]]] = [
            ("github-copilot", copilot)
        ]
        if self.settings.openai_api_key_value:
            providers.append(("openai-api", openai))
        if self.settings.gemini_api_key_value:
            providers.append(("gemini-api", gemini))
        if shutil.which(self.settings.codex_executable):
            providers.append(("codex-cli", codex))
        last_validation: ValueError | None = None
        failures: list[str] = []
        for name, generate in providers:
            # Repair on the same provider once, then advance; do not restart exhausted routes.
            current_prompt = prompt
            for attempt in range(2):
                try:
                    artifact = await generate(current_prompt)
                except CopilotGenerationError as error:
                    logger.warning("artifact_provider_unavailable route=%s", name)
                    message = str(error)
                    failures.append(f"{name}: {message}")
                    if any(
                        token in message.casefold()
                        for token in ("quota", "429", "exhausted", "usage limit", "rate limit")
                    ):
                        mark_provider_exhausted(name, message)
                    break
                clear_provider_exhausted(name)
                if validate is None:
                    return artifact
                try:
                    result = validate(artifact)
                except ValueError as error:
                    last_validation = error
                    logger.warning(
                        "artifact_implementation_incomplete route=%s attempt=%s", name, attempt + 1
                    )
                    current_prompt = (
                        prompt
                        + "\n\nIMPLEMENTATION REVIEW — REVISE THE COMPLETE ARTIFACT\n"
                        + str(error)
                        + "\nPREVIOUS ARTIFACT\n"
                        + artifact.model_dump_json()
                        + load_agent_section(
                            "automation-test-generator", "Implementation repair policy"
                        )
                    )
                else:
                    logger.info("artifact_implementation_complete route=%s", name)
                    return result
        if last_validation is not None:
            if isinstance(last_validation, IncompleteImplementationError):
                logger.warning(
                    "artifact_implementation_rejected",
                    extra={
                        "event_details": {
                            "required_steps": last_validation.step_count,
                            "findings": "\n".join(last_validation.findings),
                            "provider_notes": "\n".join(last_validation.notes),
                        }
                    },
                )
                raise ValueError(last_validation.public_message) from last_validation
            raise ValueError(
                "Configured code-generation providers returned output, but it failed validation "
                "after repair attempts. Last validation issue: " + str(last_validation)
            ) from last_validation
        raise CopilotGenerationError(
            "All configured code-generation providers are unavailable. " + " ".join(failures)
        )

    async def _openai(
        self, definition: StructuredAgentDefinition[OutputModel], instructions: str, prompt: str
    ) -> OutputModel:
        try:
            async with httpx.AsyncClient(timeout=self.settings.openai_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.openai_base_url.rstrip('/')}/responses",
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key_value}"},
                    json={
                        "model": self.settings.openai_model,
                        "instructions": instructions,
                        "input": prompt,
                        "store": False,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": "code_artifact",
                                "strict": False,
                                "schema": definition.output_model.model_json_schema(),
                            }
                        },
                    },
                )
                response.raise_for_status()
            payload = response.json()
            record_provider_usage(self.settings, "openai-api", payload)
            return definition.output_model.model_validate_json(
                json_object(_openai_output_text(payload))
            )
        except httpx.HTTPStatusError as error:
            logger.warning(
                "artifact_provider_http_failure route=openai-api status=%s",
                error.response.status_code,
            )
            raise CopilotGenerationError(
                f"OpenAI code generation failed (HTTP {error.response.status_code}). "
                "Check account quota, model access and API configuration."
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            raise CopilotGenerationError(
                "OpenAI code generation is unavailable or invalid."
            ) from error

    async def _codex(
        self, definition: StructuredAgentDefinition[OutputModel], instructions: str, prompt: str
    ) -> OutputModel:
        executable = shutil.which(self.settings.codex_executable)
        if not executable:
            raise CopilotGenerationError("Codex is unavailable.")
        process = None
        try:
            with tempfile.TemporaryDirectory(prefix="reqnroll-code-") as directory:
                schema = Path(directory) / "artifact.schema.json"
                output = Path(directory) / "artifact.json"
                schema.write_text(
                    json.dumps(_strict_json_schema(definition.output_model.model_json_schema())),
                    encoding="utf-8",
                )
                command = [
                    executable,
                    "exec",
                    "--json",
                    "--ephemeral",
                    "--sandbox",
                    "read-only",
                    "--skip-git-repo-check",
                    "--output-schema",
                    str(schema),
                    "--output-last-message",
                    str(output),
                ]
                if self.settings.codex_model:
                    command.extend(["--model", self.settings.codex_model])
                command.append("-")
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=directory,
                    start_new_session=os.name == "posix",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate((instructions + "\n\n" + prompt).encode("utf-8")),
                    timeout=self.settings.codex_artifact_timeout_seconds,
                )
                fallback_output = codex_output(self.settings, stdout)
                if process.returncode != 0:
                    raise CopilotGenerationError(_codex_failure_message(stderr))
                content = output.read_text(encoding="utf-8") if output.exists() else fallback_output
                return definition.output_model.model_validate_json(json_object(content))
        except TimeoutError as error:
            logger.warning(
                "artifact_provider_timeout route=codex-cli timeout_seconds=%s",
                self.settings.codex_artifact_timeout_seconds,
            )
            raise CopilotGenerationError(
                "Codex C# generation timed out after "
                f"{self.settings.codex_artifact_timeout_seconds:g} seconds. "
                "No completed artifact was received. Increase CODEX_ARTIFACT_TIMEOUT_SECONDS "
                "for large suites or reduce the suite size."
            ) from error
        except OSError as error:
            raise CopilotGenerationError(
                "Codex C# generation could not start or read its output."
            ) from error
        except ValueError as error:
            raise CopilotGenerationError("Codex returned invalid C# artifact JSON.") from error
        finally:
            if process is not None:
                await stop_process_tree(process)

    async def _gemini(
        self, definition: StructuredAgentDefinition[OutputModel], instructions: str, prompt: str
    ) -> OutputModel:
        """Generate a schema-constrained artifact through Gemini when configured."""
        try:
            body = {
                "systemInstruction": {"parts": [{"text": instructions}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseFormat": {
                        "text": {
                            "mimeType": "application/json",
                            "schema": definition.output_model.model_json_schema(),
                        }
                    }
                },
            }
            async with httpx.AsyncClient(timeout=self.settings.gemini_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.gemini_base_url.rstrip('/')}/models/"
                    f"{self.settings.gemini_model}:generateContent",
                    headers={"x-goog-api-key": self.settings.gemini_api_key_value},
                    json=body,
                )
                response.raise_for_status()
            payload = response.json()
            record_provider_usage(self.settings, "gemini-api", payload)
            candidate = payload["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError("Gemini response was blocked or incomplete")
            content = "".join(
                part.get("text", "")
                for part in candidate["content"]["parts"]
                if not part.get("thought")
            )
            return definition.output_model.model_validate_json(json_object(content))
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            message = (
                "Gemini API quota or rate limit is exhausted."
                if status == 429
                else f"Gemini code generation failed (HTTP {status}). Check API configuration."
            )
            raise CopilotGenerationError(message) from error
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise CopilotGenerationError(
                "Gemini code generation returned an invalid or incomplete artifact."
            ) from error
