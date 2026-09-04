"""Shared GitHub Copilot session and structured-output runtime for Markdown agents."""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings

OutputModel = TypeVar("OutputModel", bound=BaseModel)
logger = logging.getLogger(__name__)


class CopilotGenerationError(RuntimeError):
    """A safe, user-facing failure produced by a Copilot-backed agent."""


class CopilotTimeoutError(CopilotGenerationError):
    """A bounded Copilot session exceeded its configured execution budget."""


@dataclass(frozen=True)
class StructuredAgentDefinition(Generic[OutputModel]):
    """Declarative executable contract paired with repository-owned Markdown policy."""

    output_model: type[OutputModel]
    timeout_error: str
    empty_error: str
    invalid_error: str


def json_object(content: str) -> str:
    """Extract one JSON object while tolerating an accidental Markdown fence."""
    value = content.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            value = "\n".join(lines[1:-1]).strip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object found")
    return value[start : end + 1]


class CopilotAgentRunner:
    """Own common SDK lifecycle, safe configuration, events, and schema validation."""

    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory

    async def invoke(
        self,
        *,
        instructions: str,
        prompt: str,
        timeout_error: str,
        empty_error: str | None = None,
        tools: list[Any] | None = None,
        capture_response: bool = True,
        timeout_seconds: float | None = None,
    ) -> str | None:
        """Run one isolated Markdown-directed Copilot session."""
        try:
            from copilot import CopilotClient
            from copilot.session_events import (
                AssistantMessageData,
                ModelCallFailureData,
                SessionErrorData,
                SessionIdleData,
            )
        except ImportError as error:
            raise CopilotGenerationError(
                "GitHub Copilot SDK is not installed. Run 'pip install -e .' and restart."
            ) from error

        factory = self.client_factory or CopilotClient
        client_options: dict[str, Any] = {
            "working_directory": str(self.settings.copilot_working_directory),
            "use_logged_in_user": not bool(self.settings.copilot_github_token),
            "mode": "copilot-cli",
        }
        if self.settings.copilot_github_token:
            client_options["github_token"] = self.settings.copilot_github_token

        supplied_tools = tools or []
        session_options: dict[str, Any] = {
            "system_message": {"mode": "append", "content": instructions},
            "streaming": False,
            "infinite_sessions": {"enabled": False},
            "available_tools": [tool.name for tool in supplied_tools],
            "skip_custom_instructions": True,
            "enable_config_discovery": False,
            "enable_skills": False,
            "enable_session_store": False,
            "memory": {"enabled": False},
            "enable_file_hooks": False,
            "enable_host_git_operations": False,
            "mcp_servers": {},
        }
        if supplied_tools:
            session_options["tools"] = supplied_tools
        if self.settings.copilot_model:
            session_options["model"] = self.settings.copilot_model

        content: str | None = None
        provider_failure: dict[str, str | int | None] | None = None
        idle = asyncio.Event()
        async with factory(**client_options) as client:
            async with await client.create_session(**session_options) as session:

                def on_event(event: Any) -> None:
                    nonlocal content, provider_failure
                    data = getattr(event, "data", None)
                    if capture_response and isinstance(data, AssistantMessageData):
                        content = data.content
                    elif isinstance(data, SessionErrorData):
                        provider_failure = {
                            "status": data.status_code,
                            "code": data.error_code,
                            "type": data.error_type,
                        }
                    elif isinstance(data, ModelCallFailureData):
                        provider_failure = {
                            "status": data.status_code,
                            "code": data.error_code,
                            "type": str(data.failure_kind or data.error_type or "model-call"),
                        }
                    elif isinstance(data, SessionIdleData):
                        idle.set()

                session.on(on_event)
                await session.send(prompt)
                try:
                    await asyncio.wait_for(
                        idle.wait(),
                        timeout_seconds or self.settings.copilot_timeout_seconds,
                    )
                except TimeoutError as error:
                    raise CopilotTimeoutError(timeout_error) from error

        if capture_response and not content and provider_failure:
            logger.warning(
                "copilot_provider_failure status=%s code=%s type=%s",
                provider_failure.get("status"),
                provider_failure.get("code"),
                provider_failure.get("type"),
                extra={
                    "event_details": {
                        key: str(value)
                        for key, value in provider_failure.items()
                        if value is not None
                    }
                },
            )
            raise CopilotGenerationError(_provider_failure_message(provider_failure))
        if capture_response and not content:
            raise CopilotGenerationError(empty_error or "GitHub Copilot returned no output.")
        return content

    async def generate_structured(
        self,
        definition: StructuredAgentDefinition[OutputModel],
        *,
        instructions: str,
        prompt: str,
        normalize: Callable[[Any], Any] | None = None,
    ) -> OutputModel:
        """Invoke an agent and validate its JSON against the declared Pydantic contract."""
        try:
            content = await self.invoke(
                instructions=instructions,
                prompt=prompt,
                timeout_error=definition.timeout_error,
                empty_error=definition.empty_error,
            )
        except CopilotGenerationError as error:
            if str(error) != definition.empty_error:
                raise
            logger.warning(
                "structured_output_empty retry=started",
                extra={"event_details": {"empty_retry": "started"}},
            )
            content = await self.invoke(
                instructions=(
                    "You are DecisionAgent in schema-recovery mode. Generate a complete test suite "
                    "from the supplied request envelope. Return exactly one JSON object matching "
                    "the output schema, with no Markdown or commentary. Preserve explicit AC-, "
                    "BR-, and NFR- identifiers. Use synthetic data and observable expected results."
                ),
                prompt=_compact_empty_retry_prompt(prompt),
                timeout_error=definition.timeout_error,
                empty_error=(
                    f"{definition.empty_error} An automatic empty-session retry also returned "
                    "no output."
                ),
            )
            logger.info(
                "structured_output_empty retry=success",
                extra={"event_details": {"empty_retry": "success"}},
            )
        try:
            return self._validate_structured(content or "", definition.output_model, normalize)
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as first_error:
            first_paths = _validation_paths(first_error)
            logger.warning(
                "structured_output_invalid repair=started fields=%s",
                ",".join(first_paths),
                extra={"event_details": {"repair": "started", "fields": ",".join(first_paths)}},
            )
            repair_prompt = _schema_repair_prompt(
                prompt, content or "", definition.output_model, first_paths
            )
            repaired = await self.invoke(
                instructions=(
                    "You repair JSON to match a supplied schema. Return exactly one JSON object, "
                    "with no Markdown fence, explanation, comments, or omitted required fields."
                ),
                prompt=repair_prompt,
                timeout_error=definition.timeout_error,
                empty_error=definition.empty_error,
            )
            try:
                result = self._validate_structured(
                    repaired or "", definition.output_model, normalize
                )
                logger.info(
                    "structured_output_repair status=success",
                    extra={"event_details": {"repair": "success"}},
                )
                return result
            except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as repair_error:
                repair_paths = _validation_paths(repair_error)
                logger.warning(
                    "structured_output_repair status=failed fields=%s",
                    ",".join(repair_paths),
                    extra={
                        "event_details": {
                            "repair": "failed",
                            "fields": ",".join(repair_paths),
                        }
                    },
                )
                raise CopilotGenerationError(
                    f"{definition.invalid_error} Automatic schema repair was unsuccessful."
                ) from repair_error

    @staticmethod
    def _validate_structured(
        content: str,
        output_model: type[OutputModel],
        normalize: Callable[[Any], Any] | None,
    ) -> OutputModel:
        payload = json.loads(json_object(content))
        if normalize is not None:
            payload = normalize(payload)
        return output_model.model_validate(payload)


def _validation_paths(error: Exception) -> list[str]:
    """Return field locations only, never rejected values or requirement content."""
    if isinstance(error, ValidationError):
        paths = [".".join(str(part) for part in item["loc"]) for item in error.errors()]
        return list(dict.fromkeys(paths))[:20]
    if isinstance(error, json.JSONDecodeError):
        return ["response-json"]
    return ["response-object"]


def _provider_failure_message(failure: dict[str, str | int | None]) -> str:
    status = failure.get("status")
    code = str(failure.get("code") or "").casefold()
    failure_type = str(failure.get("type") or "").casefold()
    if status in {402, 429} or "quota" in code or "quota" in failure_type:
        return (
            "GitHub Copilot usage quota is exhausted. Restore premium requests, switch to an "
            "eligible model/account, or wait for the quota to reset before generating again."
        )
    if status == 401 or "auth" in code:
        return "GitHub Copilot authentication expired. Sign in to Copilot again and retry."
    if status == 403 or "policy" in code or "forbidden" in code:
        return "GitHub Copilot model access was denied by the account or organization policy."
    detail = f" (status {status})" if status else ""
    return f"GitHub Copilot model call failed{detail}. Check Copilot service and account status."


def _schema_repair_prompt(
    original_prompt: str,
    invalid_content: str,
    output_model: type[BaseModel],
    validation_paths: list[str],
) -> str:
    schema = json.dumps(output_model.model_json_schema(), separators=(",", ":"))
    request_context = original_prompt.partition("\n\nOUTPUT SCHEMA\n")[0]
    return (
        "Repair the invalid response using the original request and output schema. Preserve all "
        "supported test cases and requirement mappings. Fill required fields with meaningful, "
        "request-grounded values; do not invent product behavior.\n\n"
        f"INVALID FIELD LOCATIONS\n{json.dumps(validation_paths)}\n\n"
        f"ORIGINAL REQUEST\n{request_context}\n\n"
        f"INVALID RESPONSE\n{invalid_content}\n\n"
        f"CANONICAL OUTPUT SCHEMA\n{schema}"
    )


def _compact_empty_retry_prompt(original_prompt: str) -> str:
    """Retry without the large repository policy while retaining request data and schema."""
    request, separator, schema = original_prompt.partition("\n\nOUTPUT SCHEMA\n")
    if not separator:
        return (
            f"{original_prompt}\n\nRETRY REQUIREMENT\nComplete the request now and return "
            "exactly one schema-valid JSON object."
        )
    return (
        f"{request}\n\nRECOVERY REQUIREMENTS\n"
        "Generate distinct positive, negative, boundary, authorization, failure, and recovery "
        "cases supported by the request. Every case must have non-empty steps and expected "
        "results. For BDD output include Scenario or Scenario Outline Gherkin. Do not return "
        "prose outside JSON.\n\n"
        f"OUTPUT SCHEMA\n{schema}"
    )
