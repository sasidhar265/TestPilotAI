import asyncio

import pytest

from app.agents import AgentCapability, AgentDescriptor, AgentRegistry
from app.memory import OrganizationalMemory
from app.models import (
    ExecutionMode,
    ExpandRequest,
    GenerateRequest,
)
from app.models import (
    TestCase as CaseModel,
)
from app.models import (
    TestCategory as Category,
)
from app.models import (
    TestStep as StepModel,
)
from app.models import (
    TestSuite as SuiteModel,
)
from app.services.requirement_to_test_cases import RequirementToTestCaseService


def suite() -> SuiteModel:
    return SuiteModel(
        feature_name="Sign in",
        test_cases=[
            CaseModel(
                id="TC-001",
                title="Sign in succeeds",
                objective="Verify valid credentials",
                category=Category.CRITICAL,
                priority="P0",
                execution_mode=ExecutionMode.AUTOMATION,
                feasibility_reason="Deterministic UI flow",
                steps=[StepModel(action="Sign in", expected_result="Dashboard appears")],
            )
        ],
    )


class RequirementAgent:
    descriptor = AgentDescriptor(
        runtime_id="github-copilot",
        display_name="Requirement converter",
        capabilities=frozenset({AgentCapability.REQUIREMENT_TO_TEST_CASE}),
    )

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str] | None]] = []

    async def generate(self, request, phase="initial", existing_titles=None):
        self.calls.append((phase, existing_titles))
        return suite()


def test_convert_uses_agent_then_organizational_memory(tmp_path) -> None:
    agent = RequirementAgent()
    service = RequirementToTestCaseService(
        AgentRegistry(agent), OrganizationalMemory(tmp_path / "memory.db")
    )
    request = GenerateRequest(description="A user can sign in with valid credentials")

    first = asyncio.run(service.convert(request))
    second = asyncio.run(service.convert(request))

    assert first.feature_name == "Sign in"
    assert second.feature_name == "Sign in"
    assert agent.calls == [("initial", None)]


def test_expand_forwards_existing_titles_without_caching(tmp_path) -> None:
    agent = RequirementAgent()
    service = RequirementToTestCaseService(
        AgentRegistry(agent), OrganizationalMemory(tmp_path / "memory.db")
    )
    expansion = ExpandRequest(
        request=GenerateRequest(description="A user can sign in with valid credentials"),
        existing_titles=["Sign in succeeds"],
    )

    asyncio.run(service.expand(expansion))

    assert agent.calls == [("expand", ["Sign in succeeds"])]


def test_conversion_role_fails_when_capability_is_not_declared() -> None:
    class GenericAgent(RequirementAgent):
        descriptor = AgentDescriptor(
            runtime_id="github-copilot",
            display_name="Generic test designer",
            capabilities=frozenset({AgentCapability.TEST_DESIGN}),
        )

    registry = AgentRegistry(GenericAgent())

    with pytest.raises(LookupError, match="requirement-to-test-case"):
        registry.get_requirement_to_test_case_agent()
