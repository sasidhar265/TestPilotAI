"""Generate ReqnRoll C# bindings from approved automation scenarios."""

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from app.agent_instructions import step_definition_agent_instructions
from app.agents.runner import CopilotAgentRunner, CopilotGenerationError, StructuredAgentDefinition
from app.agents.test_case_validator import ValidationReport
from app.config import Settings
from app.models import ExecutionMode, TestSuite

logger = logging.getLogger(__name__)
_GHERKIN_STEP = re.compile(r"^\s*(Given|When|Then|And|But)\s+(.+?)\s*$")
_PARAMETER_VALUE = re.compile(r'<([A-Za-z_][A-Za-z0-9_]*)>|"([^"]+)"|\b(\d+)\b')


class StepCoverage(BaseModel):
    gherkin_step: str
    status: str = Field(pattern=r"^(reused|generated|blocked)$")
    binding: str


class StepDefinitionFile(BaseModel):
    path: str = Field(pattern=r"^[A-Za-z0-9_./-]+\.cs$")
    content: str = Field(min_length=1)


class StepDefinitionArtifact(BaseModel):
    framework: str = "ReqnRoll"
    language: str = "C#"
    files: list[StepDefinitionFile] = Field(min_length=1)
    coverage: list[StepCoverage] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class StepDefinitionRequest(BaseModel):
    suite: TestSuite
    validation: ValidationReport


STEP_DEFINITION_AGENT = StructuredAgentDefinition(
    output_model=StepDefinitionArtifact,
    timeout_error="ReqnRoll step-definition generation timed out. Try again.",
    empty_error="GitHub Copilot did not return step definitions.",
    invalid_error="GitHub Copilot returned invalid ReqnRoll step-definition output.",
)


class ReqnRollStepDefinitionAgent:
    """Use the approved Copilot runtime to create reviewable C# implementation artifacts."""

    def __init__(
        self, settings: Settings, client_factory: Callable[..., Any] | None = None
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory

    async def generate(self, request: StepDefinitionRequest) -> StepDefinitionArtifact:
        if not request.validation.passed:
            raise ValueError("Step definitions require a Quality Gate-approved suite.")
        automation_cases = [
            case
            for case in request.suite.test_cases
            if case.execution_mode == ExecutionMode.AUTOMATION and case.gherkin
        ]
        if not automation_cases:
            raise ValueError(
                "The suite has no automation Gherkin to convert into step definitions."
            )

        schema = json.dumps(StepDefinitionArtifact.model_json_schema(), separators=(",", ":"))
        source = request.suite.model_copy(update={"test_cases": automation_cases}).model_dump_json()
        prompt = f"APPROVED AUTOMATION SUITE\n{source}\n\nARTIFACT SCHEMA\n{schema}"
        runner = CopilotAgentRunner(self.settings, self.client_factory)
        try:
            return await runner.generate_structured(
                STEP_DEFINITION_AGENT,
                instructions=step_definition_agent_instructions(self.settings.agent_profile),
                prompt=prompt,
            )
        except CopilotGenerationError as error:
            logger.warning(
                "reqnroll_generation provider=unavailable fallback=deterministic error_type=%s",
                type(error).__name__,
            )
            return self._fallback_artifact(request.suite.feature_name, automation_cases)

    @staticmethod
    def _fallback_artifact(feature_name: str, automation_cases: list[Any]) -> StepDefinitionArtifact:
        """Create safe ReqnRoll bindings when an AI provider cannot implement the steps."""
        steps: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for case in automation_cases:
            previous_keyword = "Given"
            for line in (case.gherkin or "").splitlines():
                match = _GHERKIN_STEP.match(line)
                if not match:
                    continue
                keyword, text = match.groups()
                if keyword in {"And", "But"}:
                    keyword = previous_keyword
                else:
                    previous_keyword = keyword
                key = (keyword, text)
                if key not in seen:
                    seen.add(key)
                    steps.append(key)

        bindings: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
        for keyword, text in steps:
            pattern, parameters = _binding_pattern(text)
            key = (keyword, pattern, tuple(parameter_type for parameter_type, _ in parameters))
            binding = bindings.setdefault(
                key,
                {"keyword": keyword, "text": text, "pattern": pattern, "parameters": parameters},
            )
            binding.setdefault("steps", []).append(text)

        used_methods: dict[str, int] = {}
        methods: list[str] = []
        coverage: list[StepCoverage] = []
        for binding in bindings.values():
            keyword = binding["keyword"]
            text = binding["text"]
            pattern = binding["pattern"]
            parameters = binding["parameters"]
            base_name = _method_name(keyword, text)
            used_methods[base_name] = used_methods.get(base_name, 0) + 1
            suffix = used_methods[base_name]
            method_name = base_name if suffix == 1 else f"{base_name}{suffix}"
            arguments = ", ".join(
                f"{parameter_type} {name}" for parameter_type, name in parameters
            )
            escaped_pattern = pattern.replace('"', '""')
            escaped_step = text.replace('"', '\\"')
            methods.append(
                f'    [{keyword}(@"{escaped_pattern}")]\n'
                f"    public void {method_name}({arguments})\n"
                "    {\n"
                f'        throw new NotImplementedException("TODO: Implement step: {escaped_step}");\n'
                "    }"
            )
            for mapped_step in binding["steps"]:
                coverage.append(
                    StepCoverage(
                        gherkin_step=f"{keyword} {mapped_step}",
                        status="generated" if mapped_step == text else "reused",
                        binding=method_name,
                    )
                )

        class_name = _method_name("", feature_name) or "GeneratedFeature"
        content = (
            "using System;\n"
            "using Reqnroll;\n\n"
            "namespace Generated.StepDefinitions;\n\n"
            "[Binding]\n"
            f"public sealed class {class_name}StepDefinitions\n"
            "{\n"
            + "\n\n".join(methods)
            + "\n}\n"
        )
        return StepDefinitionArtifact(
            files=[
                StepDefinitionFile(
                    path=f"StepDefinitions/{class_name}StepDefinitions.cs", content=content
                )
            ],
            coverage=coverage,
            notes=[
                "AI implementation was unavailable, so deterministic ReqnRoll bindings were generated.",
                "Replace each NotImplementedException TODO with project-specific page, API, or service calls.",
            ],
        )


def _binding_pattern(text: str) -> tuple[str, list[tuple[str, str]]]:
    parts: list[str] = []
    parameters: list[tuple[str, str]] = []
    cursor = 0
    counts: dict[str, int] = {}
    for index, match in enumerate(_PARAMETER_VALUE.finditer(text), 1):
        parts.append(re.escape(text[cursor : match.start()]).replace(r"\ ", " "))
        placeholder, quoted, number = match.groups()
        if placeholder:
            parts.append("(.+)")
            raw_name, parameter_type = placeholder, "string"
        elif quoted is not None:
            parts.append('"([^"]+)"')
            raw_name, parameter_type = f"value{index}", "string"
        else:
            parts.append(r"(\d+)")
            raw_name, parameter_type = f"number{index}", "int"
        counts[raw_name] = counts.get(raw_name, 0) + 1
        name = raw_name if counts[raw_name] == 1 else f"{raw_name}{counts[raw_name]}"
        parameters.append((parameter_type, name))
        cursor = match.end()
    parts.append(re.escape(text[cursor:]).replace(r"\ ", " "))
    return f"^{''.join(parts)}$", parameters


def _method_name(keyword: str, text: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", f"{keyword} {text}")[:10]
    value = "".join(word[:1].upper() + word[1:] for word in words) or "GeneratedStep"
    return f"Step{value}" if value[0].isdigit() else value
