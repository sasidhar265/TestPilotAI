import asyncio
import json
import logging
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.agent_instructions import generation_agent_instructions
from app.agents import AgentCapability, AgentDescriptor
from app.agents.runner import (
    CopilotAgentRunner,
    CopilotGenerationError,
    StructuredAgentDefinition,
    json_object,
)
from app.config import Settings
from app.models import (
    ExecutionMode,
    GenerateRequest,
    GenerationSource,
    GenerationTarget,
    LlmModel,
    TestCase,
    TestFormat,
    TestSuite,
)

logger = logging.getLogger(__name__)

TEST_SUITE_AGENT = StructuredAgentDefinition(
    output_model=TestSuite,
    timeout_error="GitHub Copilot generation timed out. Try again.",
    empty_error="GitHub Copilot did not return a test suite.",
    invalid_error="GitHub Copilot returned output that did not match the test-suite schema.",
)


def copilot_error_message(error: Exception) -> str:
    """Return actionable Copilot failures without leaking provider responses."""
    message = str(error).casefold()
    if "auth" in message or "401" in message or "credential" in message:
        return (
            "GitHub Copilot is not authenticated. Run 'copilot login' or configure "
            "COPILOT_GITHUB_TOKEN, then restart."
        )
    if "403" in message or "forbidden" in message or "policy" in message:
        return (
            "GitHub Copilot access was denied. Ask your organization administrator to enable "
            "the Copilot CLI policy for your account."
        )
    if "rate" in message or "429" in message or "premium request" in message:
        return "GitHub Copilot usage is temporarily limited or its premium requests are exhausted."
    return "GitHub Copilot generation failed. Check the server logs and Copilot CLI status."


def system_prompt(request: GenerateRequest, profile: str = "auto-finance-quotation") -> str:
    """Load the complete behavioral policy from repository-owned Markdown."""
    return generation_agent_instructions(request.generation_target.value, profile)


def _gherkin_from_case(case: TestCase) -> str:
    given = _concise(case.preconditions[0] if case.preconditions else "prerequisites are satisfied")
    when = _concise(case.steps[0].action)
    then = _concise(case.steps[-1].expected_result)
    return "\n".join(
        [f"Scenario: {case.title}", f"  Given {given}", f"  When {when}", f"  Then {then}"]
    )


def _concise(value: str, limit: int = 100) -> str:
    """Keep fallback Gherkin readable without changing structured test detail."""
    first_clause = re.split(r"[.;\n]", " ".join(value.split()), maxsplit=1)[0].strip()
    if len(first_clause) <= limit:
        return first_clause
    shortened = first_clause[: limit + 1].rsplit(" ", 1)[0].rstrip(",:")
    return shortened or first_clause[:limit]


def finalize_suite(suite: TestSuite, request: GenerateRequest) -> TestSuite:
    """Enforce quality guarantees on untrusted Copilot output."""
    expected_mode = {
        GenerationTarget.MANUAL: ExecutionMode.MANUAL,
        GenerationTarget.AUTOMATION: ExecutionMode.AUTOMATION,
    }.get(request.generation_target)
    unique_cases: list[TestCase] = []
    seen: set[tuple[str, str]] = set()
    for case in suite.test_cases:
        fingerprint = (case.title.casefold().strip(), case.objective.casefold().strip())
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        gherkin_text = case.gherkin.strip() if case.gherkin else ""
        execution_mode = expected_mode or case.execution_mode
        if execution_mode == ExecutionMode.AUTOMATION and request.output_format == TestFormat.BDD:
            if not gherkin_text.startswith(("Scenario:", "Scenario Outline:")):
                gherkin_text = _gherkin_from_case(case)
            gherkin: str | None = gherkin_text
        else:
            gherkin = None
        scenario_group = case.scenario_group.strip() or suite.feature_name
        unique_cases.append(
            case.model_copy(
                update={
                    "scenario_group": scenario_group,
                    "execution_mode": execution_mode,
                    "gherkin": gherkin,
                }
            )
        )
    unique_cases.sort(key=lambda case: case.scenario_group.casefold())
    return suite.model_copy(
        update={
            "output_format": request.output_format,
            "test_cases": unique_cases,
        }
    )


def user_prompt(
    request: GenerateRequest,
    phase: str = "initial",
    existing_titles: list[str] | None = None,
) -> str:
    envelope = {
        "phase": phase,
        "generation_target": request.generation_target.value,
        "manual_testing_type": request.manual_testing_type.value,
        "output_format": request.output_format.value,
        "existing_titles": existing_titles or [],
        "source_material": request.description,
        "additional_context": request.additional_context,
        "business_rules": [rule.model_dump(mode="json") for rule in request.business_rules],
    }
    schema = json.dumps(TestSuite.model_json_schema(), separators=(",", ":"))
    return "REQUEST ENVELOPE\n" + json.dumps(envelope) + "\n\nOUTPUT SCHEMA\n" + schema


class GeneratorProvider(Protocol):
    descriptor: AgentDescriptor

    async def generate(
        self,
        request: GenerateRequest,
        phase: str = "initial",
        existing_titles: list[str] | None = None,
    ) -> TestSuite: ...


class CopilotGenerator:
    """Generate test suites exclusively through the official GitHub Copilot SDK."""

    descriptor = AgentDescriptor(
        runtime_id="github-copilot",
        display_name="GitHub Copilot Test Designer",
        capabilities=frozenset(
            {
                AgentCapability.REQUIREMENT_TO_TEST_CASE,
                AgentCapability.TEST_DESIGN,
                AgentCapability.NORMAL_STEPS,
                AgentCapability.SPECFLOW_BDD,
                AgentCapability.STRUCTURED_OUTPUT,
            }
        ),
    )

    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory

    async def generate(
        self,
        request: GenerateRequest,
        phase: str = "initial",
        existing_titles: list[str] | None = None,
    ) -> TestSuite:
        model = "" if request.llm_model.value == "organization-default" else request.llm_model.value
        runner = CopilotAgentRunner(
            self.settings.model_copy(update={"copilot_model": model}), self.client_factory
        )
        suite = await runner.generate_structured(
            TEST_SUITE_AGENT,
            instructions=system_prompt(request, self.settings.agent_profile),
            prompt=user_prompt(request, phase, existing_titles),
            normalize=_normalize_suite_payload,
        )
        return finalize_suite(suite, request)


class OpenAIGenerator:
    """Generate a schema-validated suite through the OpenAI Responses API."""

    descriptor = AgentDescriptor(
        runtime_id="openai-api",
        display_name="OpenAI API Test Designer",
        capabilities=CopilotGenerator.descriptor.capabilities,
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        request: GenerateRequest,
        phase: str = "initial",
        existing_titles: list[str] | None = None,
    ) -> TestSuite:
        api_key = self.settings.openai_api_key_value
        if not api_key:
            raise CopilotGenerationError(
                "OpenAI API is not configured. Add OPENAI_API_KEY to .env and restart."
            )
        body = {
            "model": self.settings.openai_model,
            "instructions": system_prompt(request, self.settings.agent_profile),
            "input": user_prompt(request, phase, existing_titles),
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "test_suite",
                    "strict": False,
                    "schema": TestSuite.model_json_schema(),
                }
            },
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.openai_timeout_seconds) as client:
                response = await client.post(
                    f"{self.settings.openai_base_url.rstrip('/')}/responses",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                )
                response.raise_for_status()
            payload = response.json()
            content = _openai_output_text(payload)
            suite = TestSuite.model_validate(
                _normalize_suite_payload(json.loads(json_object(content)))
            )
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status == 401:
                message = "OpenAI API rejected OPENAI_API_KEY. Check the Platform API key."
            elif status == 429:
                message = "OpenAI API quota or rate limit is exhausted."
            else:
                message = f"OpenAI API generation failed with HTTP {status}."
            raise CopilotGenerationError(message) from error
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as error:
            raise CopilotGenerationError(
                "OpenAI API did not return a valid test suite. Check the server logs."
            ) from error
        return finalize_suite(
            suite.model_copy(update={"generation_source": GenerationSource.OPENAI}), request
        )


class CodexGenerator:
    """Use the locally authenticated Codex CLI in non-interactive read-only mode."""

    descriptor = AgentDescriptor(
        runtime_id="codex-cli",
        display_name="Codex CLI Test Designer",
        capabilities=CopilotGenerator.descriptor.capabilities,
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        request: GenerateRequest,
        phase: str = "initial",
        existing_titles: list[str] | None = None,
    ) -> TestSuite:
        executable = shutil.which(self.settings.codex_executable)
        if executable is None:
            raise CopilotGenerationError(
                "Codex CLI is not installed or is not available on the server PATH."
            )
        prompt = (
            system_prompt(request, self.settings.agent_profile)
            + "\n\n"
            + user_prompt(request, phase, existing_titles)
        )
        try:
            with tempfile.TemporaryDirectory(prefix="reqforge-codex-") as directory:
                temp_path = Path(directory)
                schema_path = temp_path / "test-suite.schema.json"
                output_path = temp_path / "test-suite.json"
                schema_path.write_text(
                    json.dumps(_strict_json_schema(TestSuite.model_json_schema())),
                    encoding="utf-8",
                )
                command = [
                    executable,
                    "exec",
                    "--ephemeral",
                    "--sandbox",
                    "read-only",
                    "--skip-git-repo-check",
                    "--output-schema",
                    str(schema_path),
                    "--output-last-message",
                    str(output_path),
                ]
                if self.settings.codex_model:
                    command.extend(["--model", self.settings.codex_model])
                command.append("-")
                process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=directory,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(prompt.encode("utf-8")),
                    timeout=self.settings.codex_timeout_seconds,
                )
                if process.returncode != 0:
                    raise CopilotGenerationError(_codex_failure_message(stderr))
                content = (
                    output_path.read_text(encoding="utf-8")
                    if output_path.exists()
                    else stdout.decode("utf-8")
                )
                suite = TestSuite.model_validate(
                    _normalize_suite_payload(json.loads(json_object(content)))
                )
        except TimeoutError as error:
            if "process" in locals() and process.returncode is None:
                process.kill()
                await process.wait()
            raise CopilotGenerationError("Codex CLI generation timed out. Try again.") from error
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise CopilotGenerationError(
                "Codex CLI did not return a valid test suite. Check the server logs."
            ) from error
        return finalize_suite(
            suite.model_copy(update={"generation_source": GenerationSource.CODEX}), request
        )


class FallbackGenerator:
    """Route explicit selections or fail over Copilot -> OpenAI API -> Codex CLI."""

    descriptor = AgentDescriptor(
        runtime_id="automatic-fallback",
        display_name="Resilient AI Test Designer",
        capabilities=CopilotGenerator.descriptor.capabilities,
    )

    def __init__(self, settings: Settings) -> None:
        self.copilot = CopilotGenerator(settings)
        self.openai = OpenAIGenerator(settings)
        self.codex = CodexGenerator(settings)

    async def generate(
        self,
        request: GenerateRequest,
        phase: str = "initial",
        existing_titles: list[str] | None = None,
    ) -> TestSuite:
        if request.llm_model == LlmModel.OPENAI:
            return await self.openai.generate(request, phase, existing_titles)
        if request.llm_model == LlmModel.CODEX:
            return await self.codex.generate(request, phase, existing_titles)
        if request.llm_model != LlmModel.AUTO_FALLBACK:
            return await self.copilot.generate(request, phase, existing_titles)

        failures: list[str] = []
        routes: tuple[tuple[str, GeneratorProvider, LlmModel], ...] = (
            ("github-copilot", self.copilot, LlmModel.ORGANIZATION_DEFAULT),
            ("openai-api", self.openai, LlmModel.OPENAI),
            ("codex-cli", self.codex, LlmModel.CODEX),
        )
        for route, provider, selection in routes:
            try:
                selected = request.model_copy(update={"llm_model": selection})
                return await provider.generate(selected, phase, existing_titles)
            except Exception as error:
                failures.append(f"{route}: {error}")
                logger.warning(
                    "generation_provider_fallback route=%s error_type=%s",
                    route,
                    type(error).__name__,
                )
        raise CopilotGenerationError(
            "All configured AI providers are unavailable. " + " | ".join(failures)
        )


def _openai_output_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                chunks.append(str(content.get("text", "")))
    if not chunks:
        raise ValueError("OpenAI response contained no output text")
    return "\n".join(chunks)


def _strict_json_schema(value: Any) -> Any:
    """Convert Pydantic's schema to the closed object shape required by Codex."""
    if isinstance(value, list):
        return [_strict_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    schema = {
        key: _strict_json_schema(item)
        for key, item in value.items()
        if key != "default"
    }
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["additionalProperties"] = False
        schema["required"] = list(properties)
    return schema


def _codex_failure_message(stderr: bytes) -> str:
    """Classify the provider error tail without scanning the echoed user prompt."""
    diagnostic = stderr.decode("utf-8", errors="replace")
    error_tail = diagnostic.rsplit("\nERROR:", 1)[-1].casefold()
    if "invalid_json_schema" in error_tail:
        return "Codex CLI rejected the test-suite schema. Check the server logs."
    if any(marker in error_tail for marker in ("usage limit", "quota", "rate limit", "429")):
        return "Codex account usage limit is exhausted."
    if any(marker in error_tail for marker in ("not authenticated", "login required", "401")):
        return "Codex CLI is not authenticated. Run 'codex login' and restart."
    return "Codex CLI generation failed. Check the server logs."


_KEY = re.compile(r"[^a-z0-9]+")


def _key(value: object) -> str:
    return _KEY.sub("", str(value).casefold())


def _aliases(value: dict[str, Any]) -> dict[str, Any]:
    return {_key(key): item for key, item in value.items()}


def _list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in re.split(r"[,;\n]", str(value)) if item.strip()]


def _normalize_suite_payload(payload: Any) -> Any:
    """Normalize common QA presentation labels before strict Pydantic validation."""
    if isinstance(payload, list):
        payload = {"feature_name": "Generated API test suite", "test_cases": payload}
    if not isinstance(payload, dict):
        return payload
    top = _aliases(payload)
    raw_cases = top.get("testcases", top.get("tests", []))
    if not isinstance(raw_cases, list):
        return payload
    feature_name = top.get("featurename", top.get("feature", top.get("name", "API test suite")))
    normalized_cases = [
        _normalize_case(item, index) if isinstance(item, dict) else item
        for index, item in enumerate(raw_cases, 1)
    ]
    normalized = dict(payload)
    normalized["feature_name"] = feature_name
    normalized["test_cases"] = normalized_cases
    return normalized


def _normalize_case(case: dict[str, Any], index: int) -> dict[str, Any]:
    values = _aliases(case)
    title = values.get("title", values.get("scenario", f"Generated scenario {index}"))
    priority = str(values.get("priority", "P2")).upper()
    test_type = str(values.get("testtype", "")).strip()
    candidate = str(values.get("automationcandidate", values.get("executionmode", "automation")))
    automation = candidate.casefold() not in {"false", "no", "manual", "n"}
    mode = "automation" if automation else "manual"
    category = values.get("category")
    if _key(category) not in {"critical", "smoke", "sanity", "regression"}:
        category = {"P0": "critical", "P1": "smoke", "P2": "sanity"}.get(priority, "regression")
    requirements = values.get(
        "acceptancecriteriacovered", values.get("requirementid", values.get("requirementids"))
    )
    tags = _list(values.get("tags"))
    http_status = values.get("httpstatus", values.get("statuscode"))
    if http_status not in (None, ""):
        tags.append(f"http-status:{http_status}")
    if test_type:
        tags.append(f"test-type:{test_type}")
    expected = values.get("expectedresult")
    steps = _normalize_steps(values.get("steps", []), expected)
    normalized = dict(case)
    normalized.update(
        {
            "id": str(values.get("id", values.get("testcaseid", f"TC-{index:03d}"))),
            "scenario_group": str(
                values.get(
                    "scenariogroup",
                    values.get("businessscenario", values.get("feature", "General scenario")),
                )
            ),
            "title": str(title),
            "objective": str(values.get("objective", title)),
            "category": category,
            "priority": priority,
            "execution_mode": mode,
            "feasibility_reason": str(
                values.get(
                    "feasibilityreason",
                    "Deterministic API behavior suitable for automation"
                    if automation
                    else "Requires human-led evaluation",
                )
            ),
            "preconditions": _list(values.get("preconditions")),
            "steps": steps,
            "test_data": _normalize_test_data(values.get("testdata")),
            "tags": list(dict.fromkeys(tags)),
            "acceptance_criteria_covered": _list(requirements),
            "gherkin": values.get("gherkin"),
        }
    )
    return normalized


def _normalize_steps(value: Any, case_expected: Any) -> Any:
    if not isinstance(value, list):
        return value
    normalized: list[Any] = []
    for item in value:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        fields = _aliases(item)
        normalized.append(
            {
                "action": fields.get("action", fields.get("step", fields.get("description"))),
                "expected_result": fields.get(
                    "expectedresult", fields.get("result", case_expected)
                ),
            }
        )
    return normalized


def _normalize_test_data(value: Any) -> Any:
    if value in (None, ""):
        return []
    if isinstance(value, dict):
        return [
            {"name": str(name), "value": str(item), "purpose": "Generated scenario input"}
            for name, item in value.items()
        ]
    if isinstance(value, list):
        normalized = []
        for index, item in enumerate(value, 1):
            if isinstance(item, dict):
                fields = _aliases(item)
                normalized.append(
                    {
                        "name": str(fields.get("name", f"input-{index}")),
                        "value": str(fields.get("value", fields.get("data", ""))),
                        "purpose": str(fields.get("purpose", "Generated scenario input")),
                    }
                )
            else:
                normalized.append(
                    {
                        "name": f"input-{index}",
                        "value": str(item),
                        "purpose": "Generated scenario input",
                    }
                )
        return normalized
    return [{"name": "input", "value": str(value), "purpose": "Generated scenario input"}]


def create_generator(settings: Settings) -> GeneratorProvider:
    return FallbackGenerator(settings)


TestCaseGenerator = CopilotGenerator
