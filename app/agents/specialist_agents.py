"""Focused manual and automation test-generation agents."""

from app.agents.registry import AgentRegistry
from app.agents.roles import AgentKind, FunctionalAgentDescriptor
from app.models import GenerateRequest, GenerationTarget, TestFormat, TestSuite


class ManualTestCaseGeneratorAgent:
    descriptor = FunctionalAgentDescriptor(
        id="manual-test-case-generator-agent",
        name="Manual Test Case Generator",
        kind=AgentKind.MANUAL_GENERATOR,
        purpose="Generate human-led exploratory, usability, visual, and accessibility tests.",
        runtime="github-copilot",
        capabilities=("manual-tests", "exploratory-tests", "usability-tests"),
        instruction_file=".github/agents/manual-test-generator.agent.md",
    )

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    async def generate(self, request: GenerateRequest) -> TestSuite:
        targeted = request.model_copy(update={"generation_target": GenerationTarget.MANUAL})
        return await self.registry.get_test_design_agent().generate(targeted)


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
        targeted = request.model_copy(
            update={
                "generation_target": GenerationTarget.AUTOMATION,
                "output_format": TestFormat.BDD,
            }
        )
        return await self.registry.get_test_design_agent().generate(targeted)
