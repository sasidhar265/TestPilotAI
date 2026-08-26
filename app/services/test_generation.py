from app.agents import AgentRegistry
from app.agents.input_agent import InputAgent
from app.agents.storage_agent import TestStorageAgent
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.test_case_validator import TestCaseValidatorAgent
from app.memory import OrganizationalMemory
from app.models import ExpandRequest, GenerateRequest, TestSuite
from app.services.multi_agent_pipeline import MultiAgentTestPipeline


class TestGenerationService:
    """Application boundary for test-design use cases."""

    def __init__(self, registry: AgentRegistry, memory: OrganizationalMemory) -> None:
        self.registry = registry
        self.memory = memory
        self.pipeline = MultiAgentTestPipeline(
            InputAgent(),
            TestCaseGeneratorAgent(registry),
            TestCaseValidatorAgent(),
            TestStorageAgent(memory),
        )

    async def generate(self, request: GenerateRequest) -> TestSuite:
        return (await self.pipeline.run(request)).suite

    async def expand(self, expansion: ExpandRequest) -> TestSuite:
        return await self.registry.get_test_design_agent().generate(
            expansion.request,
            phase="expand",
            existing_titles=expansion.existing_titles,
        )
