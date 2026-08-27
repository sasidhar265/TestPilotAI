import pytest

from app.agents import AgentCapability, AgentDescriptor, AgentRegistry
from app.memory import OrganizationalMemory
from app.models import (
    ExecutionMode,
    GenerateRequest,
    GenerationSource,
)
from app.models import (
    TestCase as Case,
)
from app.models import (
    TestCategory as Category,
)
from app.models import (
    TestStep as Step,
)
from app.models import (
    TestSuite as Suite,
)
from app.services import TestGenerationService as GenerationService


def suite() -> Suite:
    return Suite(
        feature_name="Login",
        test_cases=[
            Case(
                id="TC-001",
                title="Valid login",
                objective="Confirm access",
                category=Category.SMOKE,
                priority="P0",
                execution_mode=ExecutionMode.AUTOMATION,
                feasibility_reason="Repeatable flow with an observable dashboard",
                steps=[Step(action="Sign in", expected_result="Dashboard appears")],
            )
        ],
    )


def test_memory_reuses_normalized_exact_requirement(tmp_path) -> None:
    memory = OrganizationalMemory(tmp_path / "memory.db")
    original = GenerateRequest(description="As a user, I want secure SIGN IN.")
    equivalent = GenerateRequest(description="  as a user,  i want secure sign in. ")

    stored = memory.put(original, suite())
    recalled = memory.get(equivalent)

    assert stored.generation_source == GenerationSource.COPILOT
    assert recalled is not None
    assert recalled.generation_source == GenerationSource.ORGANIZATIONAL_MEMORY
    assert recalled.memory_key == stored.memory_key
    assert recalled.test_cases[0].title == "Valid login"
    assert memory.count() == 1


def test_memory_separates_normal_and_bdd_formats(tmp_path) -> None:
    memory = OrganizationalMemory(tmp_path / "memory.db")
    normal = GenerateRequest(description="As a user, I want secure sign in.")
    bdd = GenerateRequest(description=normal.description, output_format="bdd")
    memory.put(normal, suite())

    assert memory.get(bdd) is None


def test_memory_separates_generation_targets(tmp_path) -> None:
    memory = OrganizationalMemory(tmp_path / "memory.db")
    both = GenerateRequest(description="As a user, I want secure sign in.")
    manual = GenerateRequest(description=both.description, generation_target="manual")
    memory.put(both, suite())

    assert memory.get(manual) is None


def test_disabled_memory_does_not_store_suite(tmp_path) -> None:
    memory = OrganizationalMemory(tmp_path / "memory.db", enabled=False)
    request = GenerateRequest(description="As a user, I want secure sign in.")
    generated = suite()

    assert memory.put(request, generated) is generated
    assert memory.count() == 0


@pytest.mark.asyncio
async def test_service_calls_copilot_once_then_returns_memory(tmp_path) -> None:
    class FakeCopilot:
        descriptor = AgentDescriptor(
            runtime_id="github-copilot",
            display_name="Fake Copilot",
            capabilities=frozenset({AgentCapability.TEST_DESIGN}),
        )

        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, request, phase="initial", existing_titles=None) -> Suite:
            self.calls += 1
            generated = suite()
            if request.generation_target == "manual":
                manual = generated.test_cases[0].model_copy(
                    update={
                        "title": "Explore unusual sign-in behavior",
                        "objective": "Identify confusing recovery behavior",
                        "execution_mode": ExecutionMode.MANUAL,
                        "feasibility_reason": "Requires human exploratory judgment",
                    }
                )
                return generated.model_copy(update={"test_cases": [manual]})
            return generated

    agent = FakeCopilot()
    service = GenerationService(AgentRegistry(agent), OrganizationalMemory(tmp_path / "memory.db"))
    request = GenerateRequest(description="As a user, I want secure sign in.")

    first = await service.generate(request)
    second = await service.generate(request)

    assert agent.calls == 2
    assert first.generation_source == GenerationSource.COPILOT
    assert second.generation_source == GenerationSource.ORGANIZATIONAL_MEMORY


@pytest.mark.asyncio
async def test_pipeline_memory_hit_does_not_start_agent_runtime(tmp_path) -> None:
    class FakeCopilot:
        descriptor = AgentDescriptor(
            runtime_id="github-copilot",
            display_name="Fake Copilot",
            capabilities=frozenset({AgentCapability.TEST_DESIGN}),
        )

        async def generate(self, request, phase="initial", existing_titles=None) -> Suite:
            raise AssertionError("Generator must not run for a memory hit")

    class FakeRuntime:
        calls = 0

        async def run(self, request):
            self.calls += 1
            raise AssertionError("Copilot runtime must not start for a memory hit")

    memory = OrganizationalMemory(tmp_path / "memory.db")
    original = GenerateRequest(description="As a user, I want secure sign in.")
    equivalent = GenerateRequest(description=" AS A USER,  I want secure sign in. ")
    memory.put(original, suite())
    service = GenerationService(AgentRegistry(FakeCopilot()), memory)
    runtime = FakeRuntime()
    service.pipeline.runtime = runtime  # type: ignore[assignment]

    result = await service.pipeline.run(equivalent)

    assert runtime.calls == 0
    assert result.suite.generation_source == GenerationSource.ORGANIZATIONAL_MEMORY
    assert result.trace[0].tool == "lookup_memory"
    assert "Copilot was not contacted" in result.trace[0].summary
