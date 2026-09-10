import pytest

from app.agents.automation_execution_agent import AutomationExecutionAgent, AutomationExecutionError
from app.config import Settings
from app.models import (
    AutomationRunRequest,
)
from app.models import (
    TestCase as CaseModel,
)
from app.models import (
    TestStep as StepModel,
)
from app.models import (
    TestSuite as SuiteModel,
)


def automation_suite() -> SuiteModel:
    return SuiteModel(
        feature_name="Approved automation",
        test_cases=[
            CaseModel(
                id="TC-001",
                title="Health is available",
                objective="Verify the service health endpoint",
                category="smoke",
                priority="P1",
                execution_mode="automation",
                feasibility_reason="Deterministic HTTP check",
                steps=[StepModel(action="Request health", expected_result="HTTP 200")],
                gherkin=("Scenario: Health is available\n"
                          "  When I request health\n  Then status is 200"),
            )
        ],
    )


@pytest.mark.asyncio
async def test_automation_agent_uses_fixed_project_and_redacts_output(monkeypatch):
    class Process:
        returncode = 0

        async def communicate(self):
            return b"Passed! - Failed: 0, Passed: 6, Skipped: 1\nAPI_AUTH_TOKEN=secret", b""

    captured = {}

    async def spawn(*command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setenv("API_AUTH_TOKEN", "secret")
    # Keep the process fake independent of the host shell and verify no shell is involved.
    monkeypatch.setattr("asyncio.create_subprocess_exec", spawn)
    report = await AutomationExecutionAgent(Settings(_env_file=None)).run(
        AutomationRunRequest(suite=automation_suite())
    )

    assert report.status == "passed"
    assert report.passed == 6
    assert report.skipped == 1
    assert "secret" not in report.output
    assert captured["command"][0:2] == ("dotnet", "test")
    assert "--no-restore" in captured["command"]
    assert "shell" not in captured["kwargs"]


@pytest.mark.asyncio
async def test_automation_agent_requires_automation_cases():
    suite = automation_suite().model_copy(
        update={
            "test_cases": [
                automation_suite().test_cases[0].model_copy(
                    update={"execution_mode": "manual"}
                )
            ]
        }
    )
    with pytest.raises(AutomationExecutionError, match="no automation cases"):
        await AutomationExecutionAgent(Settings(_env_file=None)).run(
            AutomationRunRequest(suite=suite)
        )
