"""Generate ReqnRoll C# bindings from approved automation scenarios."""

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from app.agent_instructions import load_agent_section, step_definition_agent_instructions
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.implementation_approval import (
    implementation_approval_policy,
    implementation_approval_prompt,
    require_implementation_approval,
)
from app.agents.reqnroll_implementations import common_step, support_files
from app.agents.reqnroll_memory import ReqnRollMemory
from app.agents.reqnroll_validation import IncompleteImplementationError, implementation_findings
from app.agents.runner import CopilotGenerationError, StructuredAgentDefinition
from app.agents.test_case_validator import ValidationReport
from app.automation_layout import layout_instructions, validate_layout
from app.automation_pack import csharp_assets
from app.config import Settings
from app.models import ExecutionMode, TestSuite
from app.quotation_contract import quotation_feature, quotation_sources

logger = logging.getLogger(__name__)
_GHERKIN_STEP = re.compile(r"^\s*(Given|When|Then|And|But)\s+(.+?)\s*$")
_PARAMETER_VALUE = re.compile(r'<([A-Za-z_][A-Za-z0-9_]*)>|"([^"]+)"|\b(\d+)\b')


class StepCoverage(BaseModel):
    gherkin_step: str
    status: str = Field(pattern=r"^(reused|generated|blocked)$")
    binding: str


class StepDefinitionFile(BaseModel):
    path: str = Field(pattern=r"^[A-Za-z0-9_./-]+\.(?:cs|csproj|json|Json|runsettings|md|feature)$")
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

    def generate_bindings(self, request: StepDefinitionRequest) -> StepDefinitionArtifact:
        """Generate only binding declarations; never invoke implementation generation or memory."""
        require_implementation_approval(request.validation)
        methods: dict[tuple[str, str, tuple[tuple[str, str], ...]], str] = {}
        sources: list[str] = []
        coverage: list[StepCoverage] = []
        seen: set[tuple[str, str]] = set()
        for case in request.suite.test_cases:
            if case.execution_mode != ExecutionMode.AUTOMATION:
                continue
            previous = "Given"
            for line in (case.gherkin or "").splitlines():
                match = _GHERKIN_STEP.match(line)
                if not match:
                    continue
                keyword, text = match.groups()
                keyword = previous if keyword in {"And", "But"} else keyword
                previous = keyword
                if (keyword, text) in seen:
                    continue
                seen.add((keyword, text))
                pattern, parameters = _binding_pattern(text)
                # Positional names avoid C# reserved words in outline parameter names.
                parameters = [
                    (kind, f"arg{index}") for index, (kind, _) in enumerate(parameters, 1)
                ]
                key = (keyword, pattern, tuple(parameters))
                if key not in methods:
                    name = f"{_method_name(keyword, text)}{len(methods) + 1}"
                    methods[key] = name
                    arguments = ", ".join(f"{kind} {name}" for kind, name in parameters)
                    escaped = pattern.replace('"', '""')
                    sources.append(
                        f'    [{keyword}(@"{escaped}")]\n'
                        f"    public void {name}({arguments})\n"
                        "    {\n"
                        "        throw new PendingStepException();\n"
                        "    }"
                    )
                coverage.append(
                    StepCoverage(
                        gherkin_step=f"{keyword} {text}", status="blocked", binding=methods[key]
                    )
                )
        if not sources:
            raise ValueError(
                "The suite has no automation Gherkin to convert into step definitions."
            )
        name = _method_name("", request.suite.feature_name) + "StepDefinition"
        return StepDefinitionArtifact(
            files=[
                StepDefinitionFile(
                    path=f"StepDefinitions/{name}.cs",
                    content="using Reqnroll;\n\nnamespace Generated.StepDefinitions;\n\n"
                    f"[Binding]\npublic sealed class {name}\n{{\n" + "\n\n".join(sources) + "\n}\n",
                )
            ],
            coverage=coverage,
            notes=[
                "Step definitions only: method stubs require implementation "
                "in your test framework.",
                "Steps remain pending until implemented; blocked coverage does not indicate "
                "a generation failure.",
                "No API clients, fixtures, helpers or full implementation pack were generated. "
                "Choose Full C# pack to generate implementations separately.",
            ],
        )

    async def generate(self, request: StepDefinitionRequest) -> StepDefinitionArtifact:
        artifact = await self._generate_sources(request)
        assets = csharp_assets(request.suite, artifact.notes)
        artifact.files = [
            file
            for file in artifact.files
            if not file.path.endswith(".feature")
            and file.path
            not in {"Input/TestData.Json", "Input/CaseData.Json", "Input/QuotationRequest.Json"}
        ]
        existing = {file.path for file in artifact.files}
        artifact.files.extend(
            StepDefinitionFile(path=path, content=content)
            for path, content in assets.items()
            if path not in existing
        )
        validate_layout(artifact.files)
        return artifact

    async def _generate_sources(self, request: StepDefinitionRequest) -> StepDefinitionArtifact:
        require_implementation_approval(request.validation)
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
        instructions = (
            step_definition_agent_instructions(self.settings.agent_profile)
            + layout_instructions()
            + implementation_approval_policy()
        )
        scope, scenarios = self.memory.identity(suite, self.settings.agent_profile, instructions)
        baseline = self._fallback_artifact(request.suite.feature_name, automation_cases)
        approved_quotation_sources = quotation_sources()
        expected_steps = {item.gherkin_step for item in baseline.coverage}
        knowledge: list[str] = []
        for exact, stored in self.memory.candidates(scope, scenarios):
            try:
                cached = StepDefinitionArtifact.model_validate_json(stored)
            except ValueError:
                continue
            if implementation_findings(cached, expected_steps if exact else None):
                continue
            if any(
                file.path in approved_quotation_sources
                and file.content != approved_quotation_sources[file.path]
                for file in cached.files
            ):
                continue
            try:
                validate_layout(cached.files)
            except ValueError:
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
            file.path: file
            for file in baseline.files
            if not file.path.startswith("StepDefinitions/")
        }
        prompt = (
            implementation_approval_prompt(request.validation)
            + f"APPROVED AUTOMATION SUITE\n{source}\n\nARTIFACT SCHEMA\n{schema}\n\n"
            "IMPLEMENTATION BASELINE\n"
            f"{baseline.model_dump_json()}\n\n"
            + load_agent_section(
                "reqnroll-step-definition-generator", "Implementation instructions"
            )
            + "\n\nREQUIRED COVERAGE KEYS\n"
            + json.dumps(sorted(expected_steps))
            + load_agent_section("reqnroll-step-definition-generator", "Coverage keys")
        )
        runner = ArtifactGenerationRunner(self.settings, self.client_factory)
        if knowledge:
            prompt += (
                "\n\nVALIDATED C# KNOWLEDGE FOR OVERLAPPING SCENARIOS\n"
                + "\n".join(knowledge)
                + load_agent_section("reqnroll-step-definition-generator", "Reuse conditions")
            )

        def validate(artifact: StepDefinitionArtifact) -> StepDefinitionArtifact:
            # Keep provider output immutable so repair prompts do not repeat local helpers.
            artifact = artifact.model_copy(deep=True)
            for file in artifact.files:
                if file.path in approved_quotation_sources and (
                    file.content != approved_quotation_sources[file.path]
                ):
                    raise ValueError(
                        "Reuse the supplied quotation model, builder and strategies unchanged. "
                        "Use typed builder overrides or a separate strategy for variations."
                    )
            returned_paths = {file.path for file in artifact.files}
            artifact.files.extend(
                file.model_copy(deep=True)
                for path, file in reusable_files.items()
                if path not in returned_paths
            )
            validate_layout(artifact.files)
            findings = implementation_findings(artifact, expected_steps)
            if findings:
                raise IncompleteImplementationError(findings, artifact.notes, len(expected_steps))
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
                if quotation_feature(feature_name):
                    body = body.replace("api.LoadFixture(", "api.LoadQuotationFixture(").replace(
                        "api.LoadEligibilityFixture(", "api.LoadQuotationEligibilityFixture("
                    )
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
            f"    public {class_name}StepDefinition(ApiScenario api)\n"
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
            f"public sealed class {class_name}StepDefinition\n"
            "{\n" + constructor + "\n\n".join(methods) + "\n}\n"
        )
        return StepDefinitionArtifact(
            files=[
                *(
                    [
                        StepDefinitionFile(
                            path=f"StepDefinitions/{class_name}StepDefinition.cs", content=content
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
