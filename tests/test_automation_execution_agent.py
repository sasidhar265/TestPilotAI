import asyncio
from pathlib import Path

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


def test_runner_results_show_case_ids_and_readable_titles(tmp_path):
    from app.agents.automation_execution_agent import _test_results

    results = tmp_path / "results.trx"
    results.write_text(
        '<TestRun><Results>'
        '<UnitTestResult testName="TC_UI_001_DisplayTheGenerationForm" outcome="Passed"/>'
        '<UnitTestResult testName=\'CaseId_RejectJiraPublicationWhenCondition('
        '"TC-JIRA-002","jira-unknown",null)\' outcome="Failed"/>'
        '<UnitTestResult testName="CustomScenario secret" outcome="Passed"/>'
        '</Results></TestRun>'
    )

    cases = _test_results(results, ["secret"])
    assert cases[0]["name"] == (
        "TC-UI-001 - Display the generation form and disable Generate until requirements are entered"
    )
    assert cases[1]["name"] == "TC-JIRA-002 - Reject Jira publication when a selected story is unknown"
    assert cases[1]["status"] == "Failed"
    assert cases[2]["name"] == "CustomScenario [redacted]"


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
                gherkin=(
                    "Scenario: Health is available\n  When I request health\n  Then status is 200"
                ),
            )
        ],
    )


@pytest.mark.asyncio
async def test_automation_agent_uses_fixed_project_and_redacts_output(monkeypatch):
    class Process:
        returncode = 0

        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_data(b"API_AUTH_TOKEN=secret")
            self.stdout.feed_eof()

        async def wait(self):
            return self.returncode

    captured = {}

    async def spawn(*command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        results = Path(command[command.index("--results-directory") + 1])
        results.joinpath("results.trx").write_text(
            '<TestRun xmlns="urn:test"><Results>'
            + '<UnitTestResult outcome="Passed"/>' * 6
            + '<UnitTestResult outcome="NotExecuted"/></Results></TestRun>'
        )
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
    assert "--no-restore" not in captured["command"]
    assert "shell" not in captured["kwargs"]


@pytest.mark.asyncio
async def test_repository_run_requires_no_generated_suite(monkeypatch):
    async def spawn(*args, **kwargs):
        raise OSError("dotnet unavailable")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(AutomationExecutionError, match="Unable to start"):
        await AutomationExecutionAgent(Settings(_env_file=None)).run(AutomationRunRequest())


@pytest.mark.parametrize("content", [None, "broken XML", "<TestRun/>"])
def test_missing_results_do_not_invent_failures(tmp_path, content):
    from app.agents.automation_execution_agent import _read_results

    path = tmp_path / "results.trx"
    if content is not None:
        path.write_text(content)
    passed, failed, skipped, error = _read_results(path)
    assert (passed, failed, skipped) == (0, 0, 0)
    assert error


@pytest.mark.asyncio
async def test_output_stream_is_bounded_and_redacts_chunk_boundary():
    from app.agents.automation_execution_agent import _read_output

    class Output:
        remaining = 1000

        async def read(self, size):
            assert size == 4096
            self.remaining -= 1
            if self.remaining > 0:
                return b"x" * 4096
            return {0: b"split-", -1: b"secret"}.get(self.remaining, b"")

    class Process:
        stdout = Output()

        async def wait(self):
            return 0

    output = await _read_output(Process(), ["split-secret"])
    assert len(output) == 12000
    assert output.endswith("[redacted]")
    assert "secret" not in output


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_timeout_and_cancellation_cleanup(monkeypatch, cancel):
    from app.agents import automation_execution_agent as module

    captured = {}

    class Process:
        stdout = None
        pid = 12345
        returncode = None

        async def wait(self):
            captured["waited"] = True

    async def spawn(*args, **kwargs):
        captured["env"] = kwargs["env"]
        return Process()

    async def read(*args):
        raise asyncio.CancelledError() if cancel else TimeoutError()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(module, "_read_output", read)
    monkeypatch.setattr(module.os, "killpg", lambda pid, sig: captured.update(killed=pid))
    settings = Settings(_env_file=None, api_auth_token="settings-token")
    with pytest.raises(asyncio.CancelledError if cancel else AutomationExecutionError):
        await AutomationExecutionAgent(settings).run(AutomationRunRequest(suite=automation_suite()))
    assert captured["killed"] == 12345
    assert captured["waited"]
    assert captured["env"]["API_AUTH_TOKEN"] == "settings-token"


@pytest.mark.asyncio
@pytest.mark.parametrize("dirty,results", [(False, True), (True, True), (True, False)])
async def test_prebuilt_render_run_rebuilds_installed_pack(tmp_path, monkeypatch, dirty, results):
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "automation" / "Tests.csproj"
    project.parent.mkdir()
    project.write_text('<Project Sdk="Microsoft.NET.Sdk" />')
    marker = project.parent / ".automation-build-required"
    if dirty:
        marker.write_text("installed-pack-revision")
    captured = {}

    class Process:
        returncode = 0 if results else 1

        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_eof()

        async def wait(self):
            return self.returncode

    async def spawn(*command, **kwargs):
        captured["command"] = command
        if results:
            folder = Path(command[command.index("--results-directory") + 1])
            (folder / "results.trx").write_text(
                '<TestRun><Results><UnitTestResult outcome="Passed" /></Results></TestRun>'
            )
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    report = await AutomationExecutionAgent(
        Settings(
            _env_file=None,
            automation_project_path=project,
            automation_skip_build=True,
        )
    ).run(AutomationRunRequest())
    assert ("--no-build" in captured["command"]) is (not dirty)
    assert ("--no-restore" in captured["command"]) is (not dirty)
    assert marker.exists() is (dirty and not results)
    assert report.results_available is results


@pytest.mark.asyncio
async def test_browser_only_auth_is_forwarded_as_redacted_session(tmp_path, monkeypatch):
    from app.auth import SESSION_COOKIE, valid_session

    settings = Settings(
        _env_file=None,
        api_auth_token="",
        app_username="bdd-user",
        app_password="local-verification-password",
        session_secret="s" * 32,
        user_database_path=tmp_path / "users.db",
    )
    captured = {}

    class Process:
        returncode = 0

        def __init__(self, cookie):
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_data(cookie.encode())
            self.stdout.feed_eof()

        async def wait(self):
            return 0

    async def spawn(*command, **kwargs):
        env = kwargs["env"]
        cookie = env["API_SESSION_COOKIE"]
        captured["cookie"] = cookie
        assert not env["API_AUTH_TOKEN"]
        assert cookie.startswith(SESSION_COOKIE + "=")
        assert valid_session(cookie.split("=", 1)[1], settings)
        folder = Path(command[command.index("--results-directory") + 1])
        (folder / "results.trx").write_text(
            '<TestRun><Results><UnitTestResult outcome="Passed" /></Results></TestRun>'
        )
        return Process(cookie)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    report = await AutomationExecutionAgent(settings).run(AutomationRunRequest())
    assert report.status == "passed"
    assert captured["cookie"] not in report.output
    assert "[redacted]" in report.output
