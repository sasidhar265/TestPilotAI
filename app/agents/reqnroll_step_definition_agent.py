"""Generate ReqnRoll C# bindings from approved automation scenarios."""

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from app.agent_instructions import step_definition_agent_instructions
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.reqnroll_implementations import common_step, support_files
from app.agents.reqnroll_memory import ReqnRollMemory
from app.agents.reqnroll_validation import implementation_findings
from app.agents.runner import CopilotGenerationError, StructuredAgentDefinition
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
        self.memory = ReqnRollMemory(
            settings.organizational_memory_path, settings.organizational_memory_enabled
        )

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
        suite = request.suite.model_copy(update={"test_cases": automation_cases})
        source = suite.model_dump_json()
        instructions = step_definition_agent_instructions(self.settings.agent_profile)
        scope, scenarios = self.memory.identity(suite, self.settings.agent_profile, instructions)
        baseline = self._fallback_artifact(request.suite.feature_name, automation_cases)
        expected_steps = {item.gherkin_step for item in baseline.coverage}
        knowledge: list[str] = []
        for exact, stored in self.memory.candidates(scope, scenarios):
            try:
                cached = StepDefinitionArtifact.model_validate_json(stored)
            except ValueError:
                continue
            if implementation_findings(cached, expected_steps if exact else None):
                continue
            if exact:
                for item in cached.coverage:
                    item.status = "reused"
                cached.notes.append(
                    "Reused validated C# from organizational memory for matching scenarios."
                )
                return cached
            if len(stored) <= 80000 and sum(map(len, knowledge)) + len(stored) <= 120000:
                knowledge.append(stored)
        baseline_findings = implementation_findings(baseline, expected_steps)
        if not baseline_findings:
            self.memory.put(scope, scenarios, baseline)
            return baseline
        reusable_files = {
            file.path: file for file in baseline.files if file.path.startswith("Support/")
        }
        prompt = (
            f"APPROVED AUTOMATION SUITE\n{source}\n\nARTIFACT SCHEMA\n{schema}\n\n"
            "IMPLEMENTATION BASELINE\n"
            f"{baseline.model_dump_json()}\n\n"
            "Implement executable C# method bodies and include every referenced helper file. "
            "Reuse the implemented common API bindings when compatible. Implement domain steps "
            "using the approved behavior and typed runtime configuration for missing deployment "
            "values, fixtures and independent oracle expectations. Document required configuration "
            "in notes; do not classify executable configurable code as blocked solely because "
            "those runtime values have not been supplied. Do not replace working "
            "implementations with TODOs, pending steps, empty bodies or invented assertions."
            " The Support/ files in the baseline are supplied automatically in the final "
            "download. Reference them directly and OMIT unchanged Support/ files from your "
            "response to avoid regenerating existing code. Return only binding files and "
            "new or changed helpers, plus complete coverage and notes."
            "\n\nREQUIRED COVERAGE KEYS\n"
            + json.dumps(sorted(expected_steps))
            + "\nReturn exactly one coverage item for each key above. Copy each gherkin_step "
            "verbatim, including its Given/When/Then prefix and original <parameter> text. "
            "Do not replace coverage keys with Examples values. Binding regex patterns must "
            "match substituted runtime values, while coverage keys retain original source text."
        )
        runner = ArtifactGenerationRunner(self.settings, self.client_factory)
        if knowledge:
            prompt += (
                "\n\nVALIDATED C# KNOWLEDGE FOR OVERLAPPING SCENARIOS\n"
                + "\n".join(knowledge)
                + "\nReuse compatible existing bindings and helpers for duplicate scenarios. "
                "Current approved requirements take precedence. Return one coherent complete "
                "artifact for the current suite, with no duplicate bindings or helper classes. "
                "Include all required files other than the unchanged baseline Support/ files."
            )

        def validate(artifact: StepDefinitionArtifact) -> StepDefinitionArtifact:
            # Keep provider output immutable so repair prompts do not repeat local helpers.
            artifact = artifact.model_copy(deep=True)
            returned_paths = {file.path for file in artifact.files}
            artifact.files.extend(
                file.model_copy(deep=True)
                for path, file in reusable_files.items()
                if path not in returned_paths
            )
            findings = implementation_findings(artifact, expected_steps)
            if findings:
                missing_inputs = " ".join(artifact.notes)
                raise ValueError(
                    " ".join(findings)
                    + (" Implementation context: " + missing_inputs if missing_inputs else "")
                )
            return artifact

        try:
            artifact = await runner.generate_structured(
                STEP_DEFINITION_AGENT,
                instructions=instructions,
                prompt=prompt,
                validate=validate,
            )
            self.memory.put(scope, scenarios, artifact)
            return artifact
        except CopilotGenerationError as error:
            logger.warning("reqnroll_generation failed error_type=%s", type(error).__name__)
            raise CopilotGenerationError(
                "C# implementation generation is unavailable. No incomplete files were returned. "
                + str(error)
            ) from error

    @staticmethod
    def _fallback_artifact(
        feature_name: str, automation_cases: list[Any]
    ) -> StepDefinitionArtifact:
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
            implementation = common_step(keyword, text)
            if implementation:
                pattern, parameters, body, asynchronous = implementation
            else:
                pattern, parameters = _binding_pattern(text)
                body = ""
                asynchronous = False
            binding_key = (
                keyword,
                pattern,
                tuple(parameter_type for parameter_type, _ in parameters),
            )
            binding = bindings.setdefault(
                binding_key,
                {
                    "keyword": keyword,
                    "text": text,
                    "pattern": pattern,
                    "parameters": parameters,
                    "body": body,
                    "async": asynchronous,
                    "implemented": implementation is not None,
                },
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
            arguments = ", ".join(f"{parameter_type} {name}" for parameter_type, name in parameters)
            escaped_pattern = pattern.replace('"', '""')
            return_type = "async Task" if binding["async"] else "void"
            if binding["implemented"]:
                methods.append(
                    f'    [{keyword}(@"{escaped_pattern}")]\n'
                    f"    public {return_type} {method_name}({arguments})\n"
                    "    {\n"
                    f"        {binding['body']}\n"
                    "    }"
                )
            for mapped_step in binding["steps"]:
                coverage.append(
                    StepCoverage(
                        gherkin_step=f"{keyword} {mapped_step}",
                        status=(
                            "blocked"
                            if not binding["implemented"]
                            else "generated"
                            if mapped_step == text
                            else "reused"
                        ),
                        binding=method_name,
                    )
                )

        class_name = _method_name("", feature_name) or "GeneratedFeature"
        has_implementation = any(binding["implemented"] for binding in bindings.values())
        constructor = (
            "    private readonly ApiScenario api;\n\n"
            f"    public {class_name}StepDefinitions(ApiScenario api)\n"
            "    {\n        this.api = api;\n    }\n\n"
            if has_implementation
            else ""
        )
        content = (
            "using System;\n"
            "using System.Threading.Tasks;\n"
            "using Reqnroll;\n\n"
            "namespace Generated.StepDefinitions;\n\n"
            "[Binding]\n"
            f"public sealed class {class_name}StepDefinitions\n"
            "{\n" + constructor + "\n\n".join(methods) + "\n}\n"
        )
        return StepDefinitionArtifact(
            files=[
                *(
                    [
                        StepDefinitionFile(
                            path=f"StepDefinitions/{class_name}StepDefinitions.cs", content=content
                        )
                    ]
                    if has_implementation
                    else []
                ),
                *[
                    StepDefinitionFile(path=path, content=source)
                    for path, source in support_files(automation_cases)
                ],
            ],
            coverage=coverage,
            notes=[
                "Generated deterministic ReqnRoll bindings for the approved suite.",
                "Common API steps contain implementations. Unimplemented steps are listed "
                "in coverage for AI implementation; no placeholder methods are emitted.",
                *(
                    [
                        "Target .NET 8+ with Reqnroll and Microsoft.Extensions.Http. "
                        "Save each artifact at its own path.",
                        "Set API_BASE_URL; optionally set API_BEARER_TOKEN. "
                        "For configured submission, set "
                        "API_REQUEST_METHOD and API_REQUEST_PATH from the approved contract.",
                        "JSON object/array test_data values are embedded by name "
                        "as request fixtures. "
                        "Alternatively set API_FIXTURE_FILE to a JSON object "
                        "mapping names to payloads. "
                        "Missing or conflicting fixtures must be supplied before execution.",
                    ]
                    if has_implementation
                    else []
                ),
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
