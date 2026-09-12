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

    assert agent.calls == 1
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


def test_legacy_database_retains_old_suite_until_refreshed(tmp_path) -> None:
    import sqlite3

    path = tmp_path / "legacy.db"
    memory = OrganizationalMemory(path)
    request = GenerateRequest(description="As a user, I want secure sign in.")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE test_suite_memory (memory_key TEXT PRIMARY KEY, suite_json TEXT, "
            "created_at TEXT, last_accessed_at TEXT, access_count INTEGER DEFAULT 0)"
        )
        connection.execute(
            "INSERT INTO test_suite_memory VALUES (?, ?, 'created', 'accessed', 3)",
            (memory.key_for(request), suite().model_dump_json()),
        )
    assert memory.get(request) is None
    assert memory.count() == 1
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT suite_json, access_count, generation_policy_version FROM test_suite_memory"
        ).fetchone()
    assert Suite.model_validate_json(row[0]).test_cases[0].title == "Valid login"
    assert row[1:] == (3, 0)
    updated = suite()
    updated.test_cases[0].title = "Valid credentials open the account dashboard"
    memory.put(request, updated)
    recalled = OrganizationalMemory(path).get(request)
    assert recalled is not None
    assert recalled.test_cases[0].title == updated.test_cases[0].title
    assert memory.count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("old_policy", [0, 1])
async def test_duplicate_refreshes_stale_knowledge_once_after_validation(
    tmp_path, old_policy
) -> None:
    import sqlite3
    from unittest.mock import AsyncMock

    from app.agents import TestStorageAgent
    from app.agents.test_case_validator import ValidationReport
    from app.services import MultiAgentTestPipeline
    from app.services.document_ingestion import InputAgent

    memory = OrganizationalMemory(tmp_path / "memory.db")
    request = GenerateRequest(description="As a user, I want secure sign in.")
    memory.put(request, suite())
    with sqlite3.connect(memory.path) as connection:
        connection.execute(
            "UPDATE test_suite_memory SET generation_policy_version = ?", (old_policy,)
        )
    generated = suite()
    generated.test_cases[0].title = "Valid credentials open the account dashboard"
    generator = AsyncMock()
    generator.generate.return_value = generated

    class Validator:
        passed = False

        def validate(self, request, result):
            return ValidationReport(
                passed=self.passed,
                score=100 if self.passed else 0,
                acceptance_criteria_total=0,
                acceptance_criteria_covered=0,
            )

    validator = Validator()
    pipeline = MultiAgentTestPipeline(InputAgent(), generator, validator, TestStorageAgent(memory))
    rejected = await pipeline.run(request)
    assert not rejected.validation.passed
    assert memory.get(request) is None
    with sqlite3.connect(memory.path) as connection:
        stored = connection.execute("SELECT suite_json FROM test_suite_memory").fetchone()[0]
    assert Suite.model_validate_json(stored).test_cases[0].title == "Valid login"
    validator.passed = True
    await pipeline.run(request)
    reused = await pipeline.run(request)
    assert generator.generate.await_count == 2
    assert reused.suite.generation_source == GenerationSource.ORGANIZATIONAL_MEMORY
    assert reused.suite.test_cases[0].title == generated.test_cases[0].title
    assert memory.count() == 1
