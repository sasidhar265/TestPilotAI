"""SpecForge routing agent for focused test-generation actions."""

import logging

from app.agents.output_agent import OutputAgent
from app.agents.registry import AgentRegistry
from app.agents.roles import AgentKind, FunctionalAgentDescriptor
from app.agents.specialist_agents import (
    AutomationTestCaseGeneratorAgent,
    ManualTestCaseGeneratorAgent,
)
from app.agents.test_case_validator import TestCaseValidatorAgent, ValidationReport
from app.generator import CopilotGenerationError
from app.models import ExecutionMode, GenerateRequest, GenerationTarget, TestSuite

logger = logging.getLogger(__name__)


class TestCaseGeneratorAgent:
    descriptor = FunctionalAgentDescriptor(
        id="specforge-router-agent",
        name="SpecForge Router",
        kind=AgentKind.ROUTER,
        purpose="Inspect generation intent and delegate to the correct test specialist.",
        runtime="local-router",
        capabilities=("action-routing", "manual-tests", "automation-tests", "fan-out"),
        instruction_file=".github/agents/specforge.agent.md",
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
        if request.generation_target != GenerationTarget.AUTO:
            return request.generation_target
        text = f"{request.description}\n{request.additional_context}".casefold()
        automation_markers = ("playwright", "selenium", "cypress", "automated", "automation")
        manual_markers = ("manual test", "exploratory", "usability", "human review")
        wants_automation = any(marker in text for marker in automation_markers)
        wants_manual = any(marker in text for marker in manual_markers)
        if wants_automation and not wants_manual:
            return GenerationTarget.AUTOMATION
        if wants_manual and not wants_automation:
            return GenerationTarget.MANUAL
        return GenerationTarget.BOTH

    async def generate(self, request: GenerateRequest) -> TestSuite:
        route = self.route(request)
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
            raise CopilotGenerationError(
                "Manual test cases failed the business-requirement quality gate after revision."
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
            + (
                f" Requirement: {finding.acceptance_criterion}"
                if finding.acceptance_criterion
                else ""
            )
            for finding in report.findings
            if finding.severity == "error"
        )
