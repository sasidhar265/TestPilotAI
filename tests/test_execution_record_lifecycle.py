"""Terminal lifecycle events must exist before the execution snapshot is persisted."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app import main
from app.agents.automation_execution_agent import AutomationExecutionError
from app.config import Settings
from app.models import AutomationRunReport, AutomationRunRequest
from app.observability import lifecycle_events, request_id_context
from app.services.dashboard import DashboardStore


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["passed", "failed", "error", "cancelled", "unexpected"])
async def test_execution_record_retains_terminal_event(tmp_path, monkeypatch, status):
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    request_id = str(uuid4())
    token = request_id_context.set(request_id)

    async def run(_):
        main.publish_lifecycle_event(
            "Automation Execution Agent", "run_csharp_bdd_suite", "running", "Runner started"
        )
        if status == "error":
            raise AutomationExecutionError("Runner unavailable")
        if status == "cancelled":
            raise asyncio.CancelledError()
        if status == "unexpected":
            raise RuntimeError("Unexpected runner failure")
        return AutomationRunReport(
            status=status,
            project="automation/Test.csproj",
            suite_case_count=1,
            passed=int(status == "passed"),
            failed=int(status == "failed"),
            skipped=0,
            duration_ms=100,
            output="Run finished",
        )

    monkeypatch.setattr(main.AutomationExecutionAgent, "run", AsyncMock(side_effect=run))
    try:
        if status in {"error", "cancelled"}:
            with pytest.raises(main.HTTPException):
                await main._run_automation(AutomationRunRequest(), settings)
        elif status == "unexpected":
            with pytest.raises(RuntimeError):
                await main._run_automation(AutomationRunRequest(), settings)
        else:
            await main._run_automation(AutomationRunRequest(), settings)
        snapshot = DashboardStore(settings.organizational_memory_path).snapshot("repository_checks")
        assert snapshot["active"] == []
        assert len(snapshot["history"]) == 1
        record = snapshot["history"][0]
        expected = "error" if status == "unexpected" else status
        assert record["status"] == expected
        assert [event["status"] for event in record["events"]] == ["running", expected]
        assert lifecycle_events.read(request_id)["complete"] is True
    finally:
        request_id_context.reset(token)
