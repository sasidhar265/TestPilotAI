"""Storage role for reusable, previously validated test suites."""

from app.agents.roles import AgentKind, FunctionalAgentDescriptor
from app.memory import OrganizationalMemory
from app.models import GenerateRequest, TestSuite


class TestStorageAgent:
    descriptor = FunctionalAgentDescriptor(
        id="test-storage-agent",
        name="Test Storage Agent",
        kind=AgentKind.STORAGE,
        purpose="Retrieve and store validated suites for future exact-match reuse.",
        runtime="local-sqlite",
        capabilities=("exact-match-retrieval", "validated-suite-storage", "usage-counting"),
    )

    def __init__(self, memory: OrganizationalMemory) -> None:
        self.memory = memory

    def find(self, request: GenerateRequest) -> TestSuite | None:
        return self.memory.get(request)

    def store(self, request: GenerateRequest, suite: TestSuite) -> TestSuite:
        return self.memory.put(request, suite)

    def count(self) -> int:
        return self.memory.count()
