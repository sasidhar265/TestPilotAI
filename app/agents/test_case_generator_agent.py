"""Generation role that delegates only to the approved Copilot runtime."""

from app.agents.registry import AgentRegistry
from app.agents.roles import AgentKind, FunctionalAgentDescriptor
from app.models import GenerateRequest, TestSuite


class TestCaseGeneratorAgent:
    descriptor = FunctionalAgentDescriptor(
        id="test-case-generator-agent",
        name="Manual & Automation Test Case Generator",
        kind=AgentKind.GENERATOR,
        purpose="Convert normalized requirements into manual and automated test cases.",
        runtime="github-copilot",
        capabilities=("manual-tests", "automation-tests", "normal-steps", "specflow-bdd"),
    )

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    async def generate(self, request: GenerateRequest) -> TestSuite:
        return await self.registry.get_test_design_agent().generate(request)
