from app.agents import AgentRegistry
from app.memory import OrganizationalMemory
from app.models import ExpandRequest, GenerateRequest, TestSuite


class RequirementToTestCaseService:
    """Orchestrate normalized requirement-to-test conversion.

    Document extraction belongs upstream: callers provide extracted, normalized text in a
    ``GenerateRequest``. Keeping that boundary explicit lets Word, PDF, image/OCR, and Excel
    ingestion evolve without coupling file-handling libraries to the generation agent.
    """

    def __init__(self, registry: AgentRegistry, memory: OrganizationalMemory) -> None:
        self.registry = registry
        self.memory = memory

    async def convert(self, request: GenerateRequest) -> TestSuite:
        known_suite = self.memory.get(request)
        if known_suite is not None:
            return known_suite
        agent = self.registry.get_requirement_to_test_case_agent()
        generated = await agent.generate(request)
        return self.memory.put(request, generated)

    async def expand(self, expansion: ExpandRequest) -> TestSuite:
        agent = self.registry.get_requirement_to_test_case_agent()
        return await agent.generate(
            expansion.request,
            phase="expand",
            existing_titles=expansion.existing_titles,
        )
