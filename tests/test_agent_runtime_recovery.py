import pytest

from app.agent_runtime import AgentRuntime
from app.agents.storage_agent import TestStorageAgent as StorageAgent
from app.agents.test_case_validator import TestCaseValidatorAgent
from app.config import Settings
from app.memory import OrganizationalMemory
from app.models import ExecutionMode, GenerateRequest
from app.models import TestCase as Case
from app.models import TestCategory as Category
from app.models import TestStep as Step
from app.models import TestSuite as Suite


class FallbackGenerator:
    calls = 0

    async def generate(self, request):
        self.calls += 1
        return Suite(
            feature_name="Stay signed in",
            test_cases=[
                Case(
                    id="TC-001",
                    title="Retain authenticated session",
                    objective="Verify that the opted-in session persists",
                    category=Category.CRITICAL,
                    priority="P0",
                    execution_mode=ExecutionMode.AUTOMATION,
                    feasibility_reason="Session persistence is deterministically observable",
                    steps=[
                        Step(
                            action="Restart the browser after opting to stay signed in",
                            expected_result="The authenticated account page is displayed",
                        )
                    ],
                )
            ],
        )


@pytest.mark.asyncio
async def test_incomplete_coordinator_recovers_through_governed_pipeline(tmp_path) -> None:
    generator = FallbackGenerator()
    validator = TestCaseValidatorAgent()
    storage = StorageAgent(OrganizationalMemory(tmp_path / "memory.db"))
    runtime = AgentRuntime(Settings(), generator, validator, storage)  # type: ignore[arg-type]
    request = GenerateRequest(
        description="As a user, I want an option to stay logged in between browser sessions."
    )

    outcome = await runtime._recover_incomplete_run(request, None, None, [])

    assert generator.calls == 1
    assert outcome.validation.passed
    assert [event.tool for event in outcome.trace] == [
        "coordinator_recovery",
        "design_test_suite",
        "validate_test_suite",
        "store_validated_suite",
        "finish_run",
    ]
    assert storage.find(request) is not None
