import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.services.automation_reports import generate_report, report_path
from app.services.dashboard import DashboardStore


def test_bdd_history_isolated_from_generation_and_survives_restart(tmp_path):
    store = DashboardStore(tmp_path / "memory.db")
    bdd = store.start("repository_checks")
    store.finish(bdd, "failed", {"passed": 2, "failed": 1, "not_run": 3})
    for _ in range(205):
        store.finish(store.start("test_generation"), "completed")
    current = store.start("repository_checks")
    other = store.start("automation_pack")
    try:
        snapshot = DashboardStore(tmp_path / "memory.db").snapshot("repository_checks")
        assert [r["id"] for r in snapshot["history"]] == [bdd]
        assert [r["id"] for r in snapshot["active"]] == [current]
        assert snapshot["history"][0]["details"]["not_run"] == 3
    finally:
        store.finish(current, "error")
        store.finish(other, "error")


@pytest.mark.asyncio
async def test_allure_single_html_and_redacted_native_results(tmp_path, monkeypatch):
    results = tmp_path / "allure-results"
    results.mkdir()
    (results / "test-result.json").write_text(
        json.dumps(
            {
                "name": "BDD scenario",
                "status": "failed",
                "statusDetails": {"message": "secret-value failed"},
                "steps": [
                    {
                        "name": "Then status is 200",
                        "status": "failed",
                        "attachments": [{"source": "raw.txt"}],
                    }
                ],
            }
        )
    )
    (results / "raw.txt").write_text("secret-value")
    captured = {}

    class Process:
        returncode = 0

        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_eof()

        async def wait(self):
            return 0

    async def spawn(*command, **kwargs):
        captured["command"] = command
        sanitized = Path(command[2])
        data = (sanitized / "test-result.json").read_text()
        assert "secret-value" not in data
        assert "[redacted]" in data
        assert "attachments" not in data
        assert not (sanitized / "raw.txt").exists()
        output = Path(command[command.index("--output") + 1])
        output.mkdir()
        (output / "index.html").write_text("<html>Standalone Allure</html>")
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    identifier, error = await generate_report(settings, results, ["secret-value"])
    assert error is None and identifier
    assert "--single-file" in captured["command"]
    assert report_path(settings, identifier).read_text() == "<html>Standalone Allure</html>"


@pytest.mark.asyncio
async def test_missing_allure_results_do_not_claim_report(tmp_path):
    identifier, error = await generate_report(Settings(_env_file=None), tmp_path, [])
    assert identifier is None
    assert "No Allure results" in error


@pytest.mark.asyncio
async def test_report_cli_failure_keeps_test_results_separate(tmp_path, monkeypatch):
    (tmp_path / "bdd-result.json").write_text("{}")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=OSError()))
    identifier, error = await generate_report(Settings(_env_file=None), tmp_path, [])
    assert identifier is None and error


def test_history_and_report_download_endpoints(tmp_path):
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    identifier = "a" * 32
    path = report_path(settings, identifier)
    path.parent.mkdir()
    path.write_text("<html>Real report fixture</html>")
    store = DashboardStore(settings.organizational_memory_path)
    store.finish(store.start("repository_checks"), "passed", {"report_id": identifier})
    store.finish(store.start("test_generation"), "completed")
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            history = client.get("/api/automation/history").json()
            assert len(history["history"]) == 1
            assert history["history"][0]["details"]["report_available"]
            report = client.get("/api/automation/reports/" + identifier)
            assert report.status_code == 200
            assert "attachment;" in report.headers["content-disposition"]
            assert ".html" in report.headers["content-disposition"]
            assert report.headers["cache-control"] == "no-store"
            assert client.get("/api/automation/reports/not-a-report").status_code == 404
            assert client.get("/api/automation/reports/" + "b" * 32).status_code == 404
    finally:
        app.dependency_overrides.pop(get_settings, None)


@pytest.mark.asyncio
async def test_run_endpoint_records_failures_without_inventing_counts(tmp_path, monkeypatch):
    from app import main
    from app.agents.automation_execution_agent import AutomationExecutionError
    from app.models import AutomationRunRequest

    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    monkeypatch.setattr(
        main.AutomationExecutionAgent,
        "run",
        AsyncMock(side_effect=AutomationExecutionError("Runner unavailable")),
    )
    with pytest.raises(main.HTTPException):
        await main.run_automation(AutomationRunRequest(), settings)
    record = DashboardStore(settings.organizational_memory_path).snapshot("repository_checks")[
        "history"
    ][0]
    assert record["status"] == "error"
    assert record["details"]["results_available"] is False
    assert "passed" not in record["details"]


@pytest.mark.asyncio
async def test_run_endpoint_rejects_overlapping_runs(tmp_path):
    from app import main
    from app.models import AutomationRunRequest

    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    async with main._automation_run_lock:
        with pytest.raises(main.HTTPException) as error:
            await main.run_automation(AutomationRunRequest(), settings)
    assert error.value.status_code == 409


@pytest.mark.skipif(
    __import__("os").environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check"
)
def test_bdd_chart_history_download_and_run_without_suite():
    import mimetypes
    from urllib.parse import urlparse

    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    report_id = "c" * 32
    history = [
        {
            "id": "recent",
            "operation": "repository_checks",
            "status": "failed",
            "started_at": "2026-09-11T10:00:00Z",
            "finished_at": "2026-09-11T10:00:10Z",
            "duration_ms": 10000,
            "details": {
                "passed": 2,
                "failed": 1,
                "not_run": 3,
                "report_id": report_id,
                "report_available": True,
            },
        },
        {
            "id": "older",
            "operation": "repository_checks",
            "status": "passed",
            "started_at": "2026-09-10T10:00:00Z",
            "duration_ms": 4000,
            "details": {"passed": 6, "failed": 0, "skipped": 0},
        },
        {
            "id": "unrelated",
            "operation": "test_generation",
            "status": "completed",
            "details": {"passed": 999},
        },
    ]
    submitted = []
    errors = []

    def handle(route):
        path = urlparse(route.request.url).path
        if path == "/progress" or path.startswith("/static/"):
            file = static / ("index.html" if path == "/progress" else path.removeprefix("/static/"))
            route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/automation/history":
            route.fulfill(json={"history": history, "active": [], "scope": "BDD history"})
        elif path == "/api/automation/run":
            submitted.append(route.request.post_data_json)
            route.fulfill(json={"status": "passed", "passed": 6, "failed": 0, "not_run": 0})
        elif path == "/api/workspace/rules":
            route.fulfill(json={"business_rules": []})
        elif path == "/api/workspace/standards":
            route.fulfill(json={"feature": "No tags", "automation": "BDD"})
        else:
            route.fulfill(json={"ok": True, "models": [], "events": [], "complete": True})

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", handle)
        page.goto("http://localhost/progress")
        wheel = page.locator(".bdd-wheel")
        playwright.expect(wheel).to_have_attribute("aria-label", "2 passed, 1 failed, 3 not run")
        playwright.expect(page.locator(".execution-run")).to_have_count(2)
        assert "999" not in page.locator("#dashboard-history").inner_text()
        playwright.expect(page.locator("#bdd-result-summary .allure-download")).to_have_attribute(
            "href", "/api/automation/reports/" + report_id
        )
        page.locator('[data-run-id="older"] > summary').click()
        page.locator('[data-chart-run="older"]').click()
        playwright.expect(wheel).to_have_attribute("aria-label", "6 passed, 0 failed, 0 not run")
        page.locator("#run-repository-bdd").click()
        playwright.expect(page.locator("#bdd-run-status")).to_contain_text("BDD execution passed")
        assert submitted == [{}]
        assert page.evaluate("suite") is None
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors
        browser.close()
