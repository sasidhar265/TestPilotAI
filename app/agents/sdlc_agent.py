"""Executable stage agents integrating existing BA, test design and ReqnRoll specialists."""

import ast
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, TypedDict, TypeVar

from pydantic import BaseModel

from app.agent_instructions import load_agent_instructions, load_profile_instructions
from app.agents import AgentKind, FunctionalAgentDescriptor
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.automation_execution_agent import _read_results, _test_results
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.reqnroll_step_definition_agent import (
    ReqnRollStepDefinitionAgent,
    StepDefinitionRequest,
)
from app.agents.requirements_validation import RequirementsValidationAgent
from app.agents.runner import StructuredAgentDefinition
from app.agents.workflow_agent import WorkflowAgent, test_case_request
from app.automation_pack import csharp_assets
from app.code_syntax import parse_source
from app.config import Settings
from app.dependencies import get_agent_registry, get_multi_agent_pipeline
from app.models import GenerateRequest, GenerationTarget, TestFormat
from app.quotation_contract import quotation_instructions
from app.sdlc_models import AgentDocument, CodeReview, DeliveryMission, Implementation, SourceFile
from app.services.sdlc import SDLCError
from app.services.sdlc_tools import DeliveryTools, bdd_coverage, safe_path
from app.workflow_models import ScenarioHandoff, Stories, StoryHandoff

Output = TypeVar("Output", bound=BaseModel)


class AgentInfo(TypedDict):
    stage: str
    name: str
    role: str
    specialists: list[str]


AGENT_CATALOG: list[AgentInfo] = [
    dict(
        stage="planning",
        name="Planning Agent",
        role="Scope, delivery plan and task dependencies",
        specialists=["Discovery", "Risk analysis"],
    ),
    dict(
        stage="requirements",
        name="Business Analysis Agent",
        role="BRD validation, business analysis and traceable stories",
        specialists=["BA Agent", "Requirements Validation Agent", "Story Agent"],
    ),
    dict(
        stage="design",
        name="Architecture Agent",
        role="Architecture, contracts, data models and security design",
        specialists=["Architecture", "API design"],
    ),
    dict(
        stage="development",
        name="Development Agent",
        role="Isolated source changes, independent review, build and repair",
        specialists=["Implementation", "Code Review Agent", "Build runner"],
    ),
    dict(
        stage="testing",
        name="Quality Engineering Agent",
        role="Coverage, executable automation pack and actual BDD evidence",
        specialists=["Scenario Agent", "Test Case Generator", "Quality Gate", "ReqnRoll Agent"],
    ),
    dict(
        stage="release",
        name="Release Agent",
        role="Staging promotion, PROD deployment, verification and rollback",
        specialists=["Release readiness", "Deployment runner", "Rollback runner"],
    ),
    dict(
        stage="operations",
        name="Operations Agent",
        role="Revision health verification, runbooks and support handover",
        specialists=["Health probe", "Incident readiness"],
    ),
]
SDLC_DESCRIPTORS = tuple(
    FunctionalAgentDescriptor(
        id="sdlc-" + item["stage"],
        name=item["name"],
        kind=AgentKind.DECISION,
        purpose=item["role"],
        runtime="configured-ai-providers-and-controlled-tools",
        capabilities=("versioned-handoffs", "durable-run-evidence", *item["specialists"]),
        instruction_file=".github/agents/"
        + (
            "business-analyst"
            if item["stage"] == "requirements"
            else "automation-execution"
            if item["stage"] == "testing"
            else "sdlc-" + item["stage"]
        )
        + ".agent.md",
    )
    for item in AGENT_CATALOG
)


class StageBlocked(SDLCError):
    def __init__(self, message: str, evidence: dict[str, Any] | None = None):
        super().__init__(message)
        self.evidence = evidence or {}


class SDLCStageAgents:
    def __init__(self, settings: Settings, mission: DeliveryMission, tools: DeliveryTools):
        self.settings, self.mission, self.tools = settings, mission, tools
        self.runner = ArtifactGenerationRunner(settings)

    async def generate(self, stage: str, model: type[Output], context: dict[str, Any]) -> Output:
        self.tools.on_action("agent:" + stage)
        if stage in {"release", "operations"}:
            # Manifest and execution evidence are sufficient for release/operations planning.
            context = json.loads(json.dumps(context))
            development = context.get("artifacts", {}).get("development", {})
            if "implementation" in development:
                development["implementation"].pop("files", None)
            testing = context.get("artifacts", {}).get("testing", {})
            if "pack" in testing:
                testing["pack"].pop("files", None)
        if len(json.dumps(context)) > 1_000_000:
            raise StageBlocked("Agent input exceeds its context budget; split the delivery scope")
        return await self.runner.generate_structured(
            StructuredAgentDefinition(
                model,
                f"{stage} agent timed out",
                f"{stage} agent returned no artifact",
                f"{stage} agent returned invalid output",
            ),
            instructions=load_agent_instructions("sdlc-" + stage)
            + "\n"
            + load_profile_instructions(self.settings.agent_profile)
            + "\n"
            + quotation_instructions(),
            prompt=json.dumps(context)
            + "\nOUTPUT SCHEMA\n"
            + json.dumps(model.model_json_schema()),
            llm_model=self.mission.llm_model,
        )

    async def document(self, stage: str, context: dict[str, Any]) -> dict[str, Any]:
        result = await self.generate(stage, AgentDocument, context)
        if result.blockers:
            raise StageBlocked("; ".join(result.blockers), result.model_dump(mode="json"))
        return result.model_dump(mode="json")

    async def planning(self, context: dict[str, Any]) -> dict[str, Any]:
        return await self.document("planning", context)

    async def requirements(self, context: dict[str, Any]) -> dict[str, Any]:
        request = self.mission.source_request or GenerateRequest(description=self.mission.brief)
        request = request.model_copy(
            update={
                "description": self.mission.brief,
                "additional_context": self.mission.constraints,
                "llm_model": self.mission.llm_model,
                "generation_target": GenerationTarget.AUTOMATION,
                "output_format": TestFormat.BDD,
            }
        )
        self.tools.on_action("Validate source requirements")
        validation = await RequirementsValidationAgent(self.settings).require(request)
        self.tools.on_action("Business Analyst review")
        ba = await BusinessAnalystAgent(self.settings).review(request)
        if ba.outcome != "ready_for_business_review":
            raise StageBlocked(
                "BA Agent requires clarification before design or code generation",
                dict(ba_report=ba.model_dump(mode="json")),
            )
        self.tools.on_action("Generate source-grounded stories")
        stories = await WorkflowAgent(self.settings).stories(request)
        if stories.open_questions:
            raise StageBlocked(
                "Resolve the Story Agent open questions before implementation",
                dict(stories=stories.model_dump(mode="json")),
            )
        return dict(
            document=ba.summary,
            request=request.model_dump(mode="json"),
            requirements_report=validation.model_dump(mode="json"),
            ba_report=ba.model_dump(mode="json"),
            stories=stories.model_dump(mode="json"),
            summary=f"{len(stories.stories)} source-grounded stories prepared by BA specialists",
        )

    async def design(self, context: dict[str, Any]) -> dict[str, Any]:
        result = await self.document("design", context)
        required = {
            story["id"] for story in context["artifacts"]["requirements"]["stories"]["stories"]
        }
        covered = {ref for task in result["tasks"] for ref in task["requirement_refs"]}
        if covered != required:
            raise StageBlocked("Architecture tasks must trace to every supplied story ID", result)
        return result

    async def development(self, context: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.sdlc_build_command:
            raise StageBlocked("Configure SDLC_BUILD_COMMAND before implementation")
        self.tools.on_action("Prepare isolated source checkout")
        baseline = await self.tools.prepare()
        repository = await self.tools.context()
        source = dict(**context, repository=repository, repository_baseline=baseline)
        required = {
            story["id"] for story in context["artifacts"]["requirements"]["stories"]["stories"]
        }
        changed_paths: list[str] = []
        for attempt in range(2):
            implementation = await self.generate("development", Implementation, source)
            if implementation.blockers:
                raise StageBlocked("; ".join(implementation.blockers))
            if required != set(implementation.requirements_covered):
                raise StageBlocked("Implementation does not cover every source story ID")
            for file in implementation.files:
                safe_path(self.tools.checkout, file.path)
                if file.path.endswith(".py"):
                    ast.parse(file.content, filename=file.path)
                tree = parse_source(Path(file.path).suffix, file.content)
                if tree and tree.has_error:
                    raise StageBlocked("Generated source has syntax errors: " + file.path)
            missing_context = []
            for file in implementation.files:
                path = safe_path(self.tools.checkout, file.path)
                if path.exists() and file.path not in repository:
                    repository[file.path] = path.read_text()
                    missing_context.append(file.path)
            if missing_context:
                if attempt != 0:
                    raise StageBlocked(
                        "New source replacements require another scoped review",
                        {"files": missing_context},
                    )
                source["repair_findings"] = {
                    "instruction": "Regenerate using the full original source now provided",
                    "files": missing_context,
                }
                continue
            review = await self.generate(
                "code-review",
                CodeReview,
                dict(**source, implementation=implementation.model_dump(mode="json")),
            )
            if not review.passed:
                source["repair_findings"] = review.model_dump(mode="json")
                if attempt == 0:
                    continue
                raise StageBlocked(
                    "Independent Code Review Agent rejected the implementation",
                    review.model_dump(mode="json"),
                )
            if changed_paths:
                await self.tools.reset_files(changed_paths)
            manifest = self.tools.write_files(implementation.files)
            changed_paths = [file.path for file in implementation.files]
            self.tools.on_action("Build reviewed candidate")
            build = await self.tools.command(self.settings.sdlc_build_command, self.tools.checkout)
            if build["exit_code"]:
                source["repair_findings"] = dict(
                    build=build, implementation=implementation.model_dump(mode="json")
                )
                if attempt == 0:
                    continue
                raise StageBlocked(
                    "The candidate build failed after the Development Agent repair", build
                )
            revision = await self.tools.revision()
            return dict(
                document=implementation.summary,
                summary=implementation.summary,
                implementation=implementation.model_dump(mode="json"),
                review=review.model_dump(mode="json"),
                baseline=baseline,
                build=build,
                files=manifest,
                revision=revision,
                workspace=str(self.tools.checkout),
            )
        raise StageBlocked("No validated implementation was produced")

    async def testing(self, context: dict[str, Any]) -> dict[str, Any]:
        requirements = context["artifacts"]["requirements"]
        request = GenerateRequest.model_validate(requirements["request"])
        stories = Stories.model_validate(requirements["stories"])
        self.tools.on_action("Generate traceable scenario coverage")
        scenarios = await WorkflowAgent(self.settings).scenarios(
            StoryHandoff(request=request, stories=stories)
        )
        if scenarios.open_questions:
            raise StageBlocked("Scenario Agent requires answers before test execution")
        handoff = ScenarioHandoff(request=request, stories=stories, scenarios=scenarios)
        source = test_case_request(handoff)
        pipeline = get_multi_agent_pipeline(
            registry=get_agent_registry(self.settings), settings=self.settings
        )
        self.tools.on_action("Generate test cases and apply Quality Gate")
        result = await pipeline.run(source)
        if not result.validation.passed:
            raise StageBlocked(
                "Test cases failed the existing Quality Gate",
                result.validation.model_dump(mode="json"),
            )
        covered = {
            ref for case in result.suite.test_cases for ref in case.acceptance_criteria_covered
        }
        if (
            not (
                {story.id for story in stories.stories}
                | {scenario.id for scenario in scenarios.scenarios}
            )
            <= covered
        ):
            raise StageBlocked("Test suite does not cover every story and scenario ID")
        self.tools.on_action("Generate executable ReqnRoll automation pack")
        pack = await ReqnRollStepDefinitionAgent(self.settings).generate(
            StepDefinitionRequest(
                suite=result.suite, validation=result.validation, llm_model=self.mission.llm_model
            )
        )
        files = {file.path: file.content for file in pack.files}
        files.update(csharp_assets(result.suite, pack.notes))
        if self.tools.pack.exists():
            from uuid import uuid4

            self.tools.pack.rename(self.tools.root / ("automation-previous-" + uuid4().hex[:8]))
        self.tools.pack.mkdir(parents=True, exist_ok=True)
        self.tools.write_files(
            [SourceFile(path=path, content=value) for path, value in files.items()], self.tools.pack
        )
        revision = context["artifacts"]["development"]["revision"]
        preview = await self.tools.deploy("preview", revision)
        await self.tools.health(self.settings.sdlc_preview_health_url, revision)
        reports = self.tools.pack / "TestResults" / "Reports"
        reports.mkdir(parents=True, exist_ok=True)
        self.tools.on_action("Discover and execute generated BDD pack")
        execution = await self.tools.command(
            [
                "dotnet",
                "test",
                str(self.tools.pack / "Automation.csproj"),
                "--logger",
                "trx;LogFileName=sdlc.trx",
                "--results-directory",
                str(reports),
            ],
            self.tools.pack,
            extra_env={
                "API_BASE_URL": self.settings.sdlc_preview_base_url,
                "QUALITY_LIFECYCLE_BASE_URL": self.settings.sdlc_preview_base_url,
                "API_BEARER_TOKEN": self.settings.api_bearer_token.get_secret_value(),
            },
        )
        passed, failed, skipped, error = _read_results(reports / "sdlc.trx")
        cases = [
            {key: self.tools.redact(value) for key, value in case.items()}
            for case in _test_results(reports / "sdlc.trx")
        ]
        evidence = dict(
            status="passed"
            if execution["exit_code"] == 0
            and passed > 0
            and failed == 0
            and skipped == 0
            and not error
            else "failed",
            passed=passed,
            failed=failed,
            skipped=skipped,
            test_results=cases,
            error=error,
            command=execution,
            scope="generated-sdlc-pack",
            revision=revision,
        )
        output = dict(
            document=f"ReqnRoll: {passed} passed, {failed} failed, {skipped} not executed.",
            summary=f"{passed} runner-reported BDD examples passed",
            source_request=source.model_dump(mode="json"),
            suite=result.suite.model_dump(mode="json"),
            validation=result.validation.model_dump(mode="json"),
            scenarios=scenarios.model_dump(mode="json"),
            pack=pack.model_dump(mode="json"),
            execution=evidence,
            preview=preview,
        )
        if evidence["status"] == "passed":
            raw_cases = ET.parse(reports / "sdlc.trx").getroot().findall(".//{*}UnitTestResult")
            raw_names = [case.attrib.get("testName", "") for case in raw_cases]
            for case, name in zip(cases, raw_names, strict=True):
                case["name"] = self.tools.redact(name)
            missing = bdd_coverage(files["Features/generated.feature"], raw_names)
            if missing:
                evidence.update(
                    status="failed", error="Incomplete BDD discovery: " + "; ".join(missing)
                )
        if evidence["status"] != "passed":
            raise StageBlocked(
                "Generated SDLC automation did not produce an entirely passing BDD run", output
            )
        try:
            preview["verified_after_tests"] = await self.tools.health(
                self.settings.sdlc_preview_health_url, revision
            )
        except SDLCError as error:
            evidence.update(
                status="failed", error="Preview revision could not be verified after BDD execution"
            )
            raise StageBlocked(evidence["error"], output) from error
        return output

    async def release(self, context: dict[str, Any]) -> dict[str, Any]:
        development, tests = context["artifacts"]["development"], context["artifacts"]["testing"]
        revision = development["revision"]
        if tests["execution"]["revision"] != revision or tests["execution"]["status"] != "passed":
            raise StageBlocked(
                "Release requires passing test evidence for this exact source revision"
            )
        if self.mission.target == "production" and not (
            self.settings.sdlc_production_enabled
            and self.settings.sdlc_production_command
            and self.settings.sdlc_production_health_url
            and self.settings.sdlc_rollback_command
        ):
            raise StageBlocked(
                "Configure production deployment, health and rollback before promotion"
            )
        result = await self.document("release", context)
        staging = await self.tools.deploy("staging", revision)
        staging["health"] = await self.tools.health(self.settings.sdlc_staging_health_url, revision)
        result.update(staging=staging, revision=revision, environment="staging")
        if self.mission.target == "production":
            production = await self.tools.deploy("production", revision)
            try:
                production["health"] = await self.tools.health(
                    self.settings.sdlc_production_health_url, revision
                )
            except SDLCError as error:
                previous = production["receipt"].get("previous_revision")
                if not previous or previous == revision:
                    raise StageBlocked(
                        "Production health failed and its receipt lacks a rollback revision",
                        dict(production=production),
                    ) from error
                rollback = await self.tools.deploy("rollback", previous)
                rollback["health"] = await self.tools.health(
                    self.settings.sdlc_production_health_url, previous
                )
                raise StageBlocked(
                    "Production health failed; rollback was verified. Review before retrying.",
                    dict(production=production, rollback=rollback),
                ) from error
            result.update(production=production, environment="production")
        return result

    async def operations(self, context: dict[str, Any]) -> dict[str, Any]:
        release = context["artifacts"]["release"]
        url = (
            self.settings.sdlc_production_health_url
            if release["environment"] == "production"
            else self.settings.sdlc_staging_health_url
        )
        health = await self.tools.health(url, release["revision"])
        document = await self.document("operations", dict(**context, verified_health=health))
        document.update(
            health=health, environment=release["environment"], revision=release["revision"]
        )
        return document
