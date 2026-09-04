"""OrchestratorAgent coordination and DecisionAgent specialist routing."""

import logging

from app.agents import AgentKind, AgentRegistry, FunctionalAgentDescriptor
from app.agents.output_agent import OutputAgent
from app.agents.runner import CopilotGenerationError
from app.agents.test_case_validator import TestCaseValidatorAgent, ValidationReport
from app.models import ExecutionMode, GenerateRequest, GenerationTarget, TestFormat, TestSuite
from app.observability import publish_lifecycle_event

logger = logging.getLogger(__name__)


class ManualTestCaseGeneratorAgent:
    descriptor = FunctionalAgentDescriptor(
        id="manual-test-case-generator-agent",
        name="Manual Test Case Generator",
        kind=AgentKind.MANUAL_GENERATOR,
        purpose="Generate governed human-led tests through the selected manual discipline.",
        runtime="github-copilot",
        capabilities=(
            "manual-tests",
            "manual-ui-tests",
            "manual-performance-tests",
            "manual-database-tests",
        ),
        instruction_file=".github/agents/manual-test-generator.agent.md",
    )

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry
        self.specialist = ManualTestingSpecialistAgent()

    async def generate(self, request: GenerateRequest) -> TestSuite:
        publish_lifecycle_event(
            "Manual Test Generator",
            "generate_manual",
            "running",
            "Generating human-led scenarios from the current governed request envelope.",
        )
        targeted = self.specialist.prepare(request)
        suite = await self.registry.get_test_design_agent().generate(targeted)
        publish_lifecycle_event(
            "Manual Test Generator",
            "generate_manual",
            "success",
            f"Generated {len(suite.test_cases)} manual candidate cases.",
        )
        return suite


class ManualTestingSpecialistAgent:
    """Preserve the selected manual discipline in the governed request envelope."""

    descriptor = FunctionalAgentDescriptor(
        id="manual-testing-specialist-agent",
        name="Manual Testing Specialist Agent",
        kind=AgentKind.MANUAL_SPECIALIST,
        purpose=(
            "Design manual API, UI, performance, or database test coverage "
            "from requirements and governed business rules."
        ),
        runtime="local-router",
        capabilities=(
            "manual-ui-tests",
            "manual-api-tests",
            "manual-performance-tests",
            "manual-database-tests",
            "discipline-routing",
        ),
        instruction_file=".github/agents/manual-testing-specialist.agent.md",
    )

    def prepare(self, request: GenerateRequest) -> GenerateRequest:
        return request.model_copy(
            update={
                "generation_target": GenerationTarget.MANUAL,
                "output_format": TestFormat.NORMAL,
            }
        )


class AutomationTestCaseGeneratorAgent:
    descriptor = FunctionalAgentDescriptor(
        id="automation-test-case-generator-agent",
        name="Automation Test Case Generator",
        kind=AgentKind.AUTOMATION_GENERATOR,
        purpose="Generate deterministic, repeatable UI, API, and integration automation tests.",
        runtime="github-copilot",
        capabilities=(
            "automation-tests",
            "ui-tests",
            "api-tests",
            "integration-tests",
            "specflow-bdd",
        ),
        instruction_file=".github/agents/automation-test-generator.agent.md",
    )

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    async def generate(self, request: GenerateRequest) -> TestSuite:
        publish_lifecycle_event(
            "Automation Test Generator",
            "generate_automation",
            "running",
            "Generating repeatable BDD scenarios from the current governed request envelope.",
        )
        targeted = request.model_copy(
            update={
                "generation_target": GenerationTarget.AUTOMATION,
                "output_format": TestFormat.BDD,
            }
        )
        suite = await self.registry.get_test_design_agent().generate(targeted)
        publish_lifecycle_event(
            "Automation Test Generator",
            "generate_automation",
            "success",
            f"Generated {len(suite.test_cases)} automation candidate cases.",
        )
        return suite


class DecisionAgent:
    descriptor = FunctionalAgentDescriptor(
        id="decision-agent",
        name="DecisionAgent",
        kind=AgentKind.DECISION,
        purpose=("Route OrchestratorAgent scenarios into manual test cases or BDD Gherkin."),
        runtime="local-router",
        capabilities=("scenario-transformation", "manual-tests", "bdd-gherkin", "fan-out"),
        instruction_file=".github/agents/reqforge.agent.md",
    )

    def __init__(
        self,
        registry: AgentRegistry,
        quality_gate: TestCaseValidatorAgent | None = None,
        knowledge_source: OutputAgent | None = None,
    ) -> None:
        self.manual = ManualTestCaseGeneratorAgent(registry)
        self.automation = AutomationTestCaseGeneratorAgent(registry)
        self.quality_gate = quality_gate or TestCaseValidatorAgent()
        self.knowledge_source = knowledge_source

    def route(self, request: GenerateRequest) -> GenerationTarget:
        """Select specialists from the normalized output intent supplied by OrchestratorAgent."""
        if request.generation_target != GenerationTarget.AUTO:
            return request.generation_target
        if request.output_format == TestFormat.BDD:
            return GenerationTarget.AUTOMATION
        return GenerationTarget.MANUAL

    async def transform(self, request: GenerateRequest) -> TestSuite:
        route = self.route(request)
        publish_lifecycle_event(
            "DecisionAgent",
            "route_specialists",
            "success",
            f"Received OrchestratorAgent scenario intent and selected the {route.value} specialist route.",
        )
        request = self._with_organizational_knowledge(request)
        if route == GenerationTarget.MANUAL:
            return await self._generate_validated_manual(request)
        if route == GenerationTarget.AUTOMATION:
            return await self._generate_validated_automation(request)

        # The Copilot SDK owns a local CLI process and is not safe to fan out through
        # multiple simultaneous client sessions. Keep specialist calls deterministic.
        automation = await self._generate_validated_automation(request)
        try:
            manual = await self._generate_validated_manual(request)
        except CopilotGenerationError:
            logger.warning(
                "specialist_quality_gate route=manual outcome=excluded "
                "fallback=validated-automation"
            )
            return automation.model_copy(
                update={
                    "coverage_notes": list(automation.coverage_notes)
                    + [
                        "Manual scenarios were excluded because they did not pass the "
                        "business-requirement quality gate."
                    ]
                }
            )
        cases = manual.test_cases + automation.test_cases
        cases = [
            case.model_copy(update={"id": f"TC-{index:03d}"}) for index, case in enumerate(cases, 1)
        ]
        return TestSuite(
            feature_name=manual.feature_name or automation.feature_name,
            output_format=request.output_format,
            assumptions=list(dict.fromkeys(manual.assumptions + automation.assumptions)),
            coverage_notes=list(dict.fromkeys(manual.coverage_notes + automation.coverage_notes)),
            test_cases=cases,
        )

    def _with_organizational_knowledge(self, request: GenerateRequest) -> GenerateRequest:
        if self.knowledge_source is None:
            return request
        knowledge = self.knowledge_source.knowledge_for(request)
        if not knowledge:
            return request
        return request.model_copy(
            update={"additional_context": f"{request.additional_context}\n\n{knowledge}".strip()}
        )

    async def _generate_validated_manual(self, request: GenerateRequest) -> TestSuite:
        suite = await self.manual.generate(request)
        report = self.quality_gate.validate(request, suite, expected_mode=ExecutionMode.MANUAL)
        if report.passed:
            return suite

        revision = request.model_copy(
            update={
                "additional_context": (
                    request.additional_context
                    + "\n\nMANUAL QUALITY GATE CORRECTIONS REQUIRED\n"
                    + self._revision_instructions(report)
                ).strip()
            }
        )
        revised = await self.manual.generate(revision)
        final_report = self.quality_gate.validate(
            request, revised, expected_mode=ExecutionMode.MANUAL
        )
        if not final_report.passed:
            details = self._failure_summary(final_report)
            logger.warning("specialist_quality_gate route=manual outcome=failed details=%s", details)
            raise CopilotGenerationError(
                "Manual test cases failed the business-requirement quality gate after revision. "
                f"Remaining issues: {details}"
            )
        return revised

    async def _generate_validated_automation(self, request: GenerateRequest) -> TestSuite:
        suite = await self.automation.generate(request)
        report = self.quality_gate.validate(request, suite, expected_mode=ExecutionMode.AUTOMATION)
        if report.passed:
            return suite

        revision = request.model_copy(
            update={
                "additional_context": (
                    request.additional_context
                    + "\n\nAUTOMATION QUALITY GATE CORRECTIONS REQUIRED\n"
                    + self._revision_instructions(report)
                ).strip()
            }
        )
        revised = await self.automation.generate(revision)
        final_report = self.quality_gate.validate(
            request, revised, expected_mode=ExecutionMode.AUTOMATION
        )
        if not final_report.passed:
            raise CopilotGenerationError(
                "Automation test cases failed the business-requirement quality gate after revision."
            )
        return revised

    @staticmethod
    def _revision_instructions(report: ValidationReport) -> str:
        return "\n".join(
            f"- {finding.message}"
            + (f" Cases: {', '.join(finding.test_case_ids)}." if finding.test_case_ids else "")
            + (
                f" Requirement: {finding.acceptance_criterion}"
                if finding.acceptance_criterion
                else ""
            )
            for finding in report.findings
            if finding.severity == "error"
        )

    @staticmethod
    def _failure_summary(report: ValidationReport) -> str:
        issues: list[str] = []
        for finding in report.findings:
            if finding.severity != "error":
                continue
            affected = f" ({', '.join(finding.test_case_ids)})" if finding.test_case_ids else ""
            criterion = f" [{finding.acceptance_criterion}]" if finding.acceptance_criterion else ""
            issues.append(f"{finding.dimension.value}{affected}{criterion}")
        return ", ".join(dict.fromkeys(issues)) or "unspecified validation error"


class OrchestratorAgent:
    """Ingest normalized requirements, design scenario intent, and coordinate DecisionAgent."""

    descriptor = FunctionalAgentDescriptor(
        id="orchestrator-agent",
        name="OrchestratorAgent",
        kind=AgentKind.ORCHESTRATOR,
        purpose=(
            "Read normalized UI or BRD input, design risk-based scenarios, and direct "
            "DecisionAgent routing."
        ),
        runtime="local-orchestrator",
        capabilities=(
            "ui-input-ingestion",
            "requirement-analysis",
            "scenario-design",
            "decision-agent-orchestration",
        ),
        instruction_file=".github/agents/testpilot-coordinator.agent.md",
    )

    def __init__(
        self,
        registry: AgentRegistry,
        quality_gate: TestCaseValidatorAgent | None = None,
        knowledge_source: OutputAgent | None = None,
    ) -> None:
        self.decision_agent = DecisionAgent(registry, quality_gate, knowledge_source)

    def route(self, request: GenerateRequest) -> GenerationTarget:
        """Compatibility boundary; DecisionAgent owns the specialist routing decision."""
        return self.decision_agent.route(request)

    async def generate(self, request: GenerateRequest) -> TestSuite:
        """Treat the validated request as ingested UI data and send scenarios to DecisionAgent."""
        publish_lifecycle_event(
            "OrchestratorAgent",
            "analyze_and_handoff",
            "success",
            "Analyzed normalized requirements and transferred scenario intent to DecisionAgent.",
        )
        return await self.decision_agent.transform(request)


# Preserve former public names for callers while exposing the renamed responsibilities.
ReqForgeTransformerAgent = DecisionAgent
QAMasterAgent = OrchestratorAgent
TestCaseGeneratorAgent = OrchestratorAgent
