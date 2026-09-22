"""Progress execution logs expose retained run evidence and useful filters."""

import mimetypes
import os
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

import pytest


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_execution_logs_filters_and_per_run_details():
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    bdd = {
        "id": "bdd-1", "operation": "repository_checks", "status": "failed", "request_id": "corr-123",
        "started_at": "2026-09-20T10:00:00Z", "finished_at": "2026-09-20T10:01:00Z",
        "duration_ms": 60000,
        "events": [
            {"timestamp": "2026-09-20T10:00:10Z", "agent": "Automation Execution Agent",
             "action": "run_csharp_bdd_suite", "status": "running", "summary": "BDD runner started"},
            {"timestamp": "2026-09-20T10:00:50Z", "agent": "Automation Execution Agent",
             "action": "bdd_report", "status": "success", "summary": "Report prepared"},
        ],
        "details": {"project": "QualityLifecycle.Automation", "passed": 2, "failed": 1,
                    "not_run": 0, "output": "Runner started\nWARN retry\nRunner failure detail",
                    "report_id": "a" * 32, "report_available": True,
                    "test_results": [{"name": "Quotation scenario", "status": "Failed",
                                      "error": "Expected 200, got 400"}]},
    }
    case = {
        "id": "case-1", "operation": "case_execution", "status": "completed",
        "started_at": "2026-09-21T11:00:00Z", "finished_at": "2026-09-21T11:00:01Z",
        "duration_ms": 1000,
        "details": {"feature": "PCP quotation", "cases": [
            {"id": "TC-1", "title": "Valid PCP quote", "execution": "passed", "mode": "manual"},
            {"id": "TC-2", "title": "Invalid PCP quote", "execution": "failed", "mode": "manual",
             "actual_result": "Expected rejection, received a quote"},
        ]},
    }
    case["details"]["cases"].extend(
        {"id": f"TC-{number}", "title": f"Quotation case {number}", "execution": "passed"}
        for number in range(3, 24)
    )
    case_runs = [case]
    for number in range(2, 13):
        older = deepcopy(case)
        older["id"] = f"case-{number}"
        older["started_at"] = f"2026-09-{21 - number:02d}T11:00:00Z"
        case_runs.append(older)
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route(request):
            path = urlparse(request.request.url).path
            if path == "/progress" or path.startswith("/static/"):
                file = static / ("index.html" if path == "/progress" else path.removeprefix("/static/"))
                request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
            elif path == "/api/dashboard":
                request.fulfill(json={"history": case_runs, "active": [], "usage": {}})
            elif path == "/api/automation/history":
                request.fulfill(json={"history": [bdd], "active": [], "scope": "Retained", "timeout_seconds": 900})
            elif path == "/api/logs":
                request.fulfill(json={"entries": [
                    {"timestamp": "2026-09-20T10:00:30Z", "level": "INFO", "message": "Runner checkpoint"}
                ]})
            else:
                request.fulfill(json={"models": [], "events": [], "history": [], "active": [], "business_rules": []})

        page.route("**/*", route)
        page.goto("http://localhost/progress")
        playwright.expect(page.locator("#progress-dashboard-view")).to_be_visible()
        page.locator('[data-execution-view="logs"]').click()
        playwright.expect(page.locator("#execution-logs-rows tr")).to_have_count(10)
        playwright.expect(page.locator("#execution-logs-metrics strong")).to_have_text(["13", "0", "13", "0"])
        page.locator("#execution-logs-next").click()
        playwright.expect(page.locator("#execution-logs-rows tr")).to_have_count(3)
        playwright.expect(page.locator("#execution-logs-page-number")).to_have_text("Page 2 of 2")
        page.locator("#execution-logs-previous").click()
        page.locator("#execution-logs-type").select_option("case_execution")
        playwright.expect(page.locator("#execution-logs-rows tr")).to_have_count(10)
        playwright.expect(page.locator("#execution-logs-page-number")).to_have_text("Page 1 of 2")
        page.locator("#execution-logs-rows .execution-log-view").first.click()
        playwright.expect(page.locator("#execution-detail-panel-execution")).to_be_visible()
        playwright.expect(page.locator(".execution-details-hero")).to_contain_text("PCP quotation")
        playwright.expect(page.locator(".execution-details-group")).to_have_count(2)
        playwright.expect(page.locator("#execution-detail-panel-execution")).to_contain_text("Not recorded")
        playwright.expect(page.locator("#execution-log-allure-download")).to_be_hidden()
        page.locator("#execution-detail-tab-cases").click()
        playwright.expect(page.locator("#execution-detail-panel-cases")).to_contain_text("Valid PCP quote")
        playwright.expect(page.locator("#execution-detail-panel-cases")).to_contain_text("TC-2")
        page.locator("#execution-case-rows .test-failure-disclosure").first.locator("summary").click()
        playwright.expect(page.locator("#execution-case-rows .test-failure-evidence")).to_contain_text(
            "Expected rejection, received a quote"
        )
        page.locator("#execution-detail-tab-failures").click()
        playwright.expect(page.locator("#execution-detail-panel-failures .test-failure-card")).to_contain_text(
            "Expected rejection, received a quote"
        )
        page.locator("#execution-detail-tab-cases").click()
        playwright.expect(page.locator("#execution-case-rows tr")).to_have_count(10)
        page.locator("#execution-case-next").click()
        playwright.expect(page.locator("#execution-case-rows tr")).to_have_count(10)
        page.locator("#execution-case-next").click()
        playwright.expect(page.locator("#execution-case-rows tr")).to_have_count(3)
        playwright.expect(page.locator("#execution-case-page-number")).to_have_text("Page 3 of 3")
        page.locator("#execution-case-search").fill("Quotation case 23")
        playwright.expect(page.locator("#execution-case-rows tr")).to_have_count(1)
        page.locator("#execution-case-search").fill("")
        page.screenshot(path="/tmp/execution-cases-desktop.png")
        playwright.expect(page.locator("#execution-detail-panel-execution")).to_be_hidden()
        page.locator("#execution-detail-tab-transactions").click()
        playwright.expect(page.locator("#execution-detail-panel-transactions")).to_be_visible()
        page.locator("#execution-log-detail-close").click()
        page.locator("#execution-logs-type").select_option("repository_checks")
        page.locator("#execution-logs-status").select_option("failed")
        playwright.expect(page.locator("#execution-logs-rows tr")).to_have_count(1)
        page.locator("#execution-logs-rows .execution-log-view").click()
        playwright.expect(page.locator("#execution-detail-panel-execution")).to_be_visible()
        playwright.expect(page.locator(".execution-details-hero")).to_contain_text("QualityLifecycle.Automation")
        playwright.expect(page.locator("#execution-log-allure-download")).to_have_attribute(
            "href", "/api/automation/reports/" + "a" * 32
        )
        page.locator("#execution-detail-tab-report").click()
        playwright.expect(page.locator("#execution-detail-panel-report")).to_be_visible()
        playwright.expect(page.locator("#execution-detail-panel-report .execution-report-donut")).to_have_attribute(
            "aria-label", "2 passed, 1 failed, 0 skipped"
        )
        playwright.expect(page.locator("#execution-detail-panel-report .execution-report-outcomes article")).to_have_count(4)
        playwright.expect(page.locator("#execution-detail-panel-report")).to_contain_text("Not recorded")
        page.screenshot(path="/tmp/execution-report-desktop.png")
        page.locator("#execution-detail-tab-overview").click()
        playwright.expect(page.locator("#execution-detail-panel-overview .execution-overview-timeline li")).to_have_count(4)
        playwright.expect(page.locator(".execution-overview-summary")).to_contain_text("failed")
        page.screenshot(path="/tmp/execution-overview-desktop.png")
        page.locator("#execution-detail-tab-activity").click()
        playwright.expect(page.locator(".execution-agent-timeline li")).to_have_count(2)
        playwright.expect(page.locator("#execution-detail-panel-activity")).to_contain_text("BDD runner started")
        playwright.expect(page.locator("#execution-detail-panel-activity")).to_contain_text("Report prepared")
        page.screenshot(path="/tmp/execution-agent-activity-desktop.png")
        page.locator("#execution-detail-tab-failures").click()
        playwright.expect(page.locator("#execution-detail-panel-failures")).to_contain_text("Quotation scenario")
        playwright.expect(page.locator("#execution-detail-panel-failures")).to_contain_text("Expected 200, got 400")
        page.locator("#execution-detail-tab-errors").click()
        playwright.expect(page.locator("#execution-detail-panel-errors .test-failure-card")).to_contain_text(
            "Expected 200, got 400"
        )
        page.locator("#execution-detail-tab-logs").click()
        playwright.expect(page.locator("#execution-detail-panel-logs")).to_contain_text("Runner failure detail")
        playwright.expect(page.locator(".execution-technical-line")).to_have_count(3)
        page.locator("#execution-technical-search").fill("failure")
        playwright.expect(page.locator(".execution-technical-line")).to_have_count(1)
        page.locator("#execution-technical-search").fill("")
        playwright.expect(page.locator(".execution-app-log-list article")).to_have_count(1)
        page.screenshot(path="/tmp/execution-technical-logs-desktop.png")
        page.locator("#execution-detail-tab-logs").focus()
        page.keyboard.press("Home")
        playwright.expect(page.locator("#execution-detail-tab-execution")).to_have_attribute("aria-selected", "true")
        page.screenshot(path="/tmp/execution-log-detail-desktop.png")
        page.keyboard.press("Escape")
        playwright.expect(page.locator("#execution-log-detail")).not_to_be_visible()
        page.locator("#execution-logs-search").fill("missing")
        playwright.expect(page.locator("#execution-logs-rows")).to_contain_text("No executions match")
        page.locator("#execution-logs-search").fill("")
        page.screenshot(path="/tmp/execution-logs-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        playwright.expect(page.locator("#execution-logs-rows .execution-log-view")).to_be_visible()
        page.locator("#execution-logs-rows .execution-log-view").click()
        playwright.expect(page.locator("#execution-log-allure-download")).to_be_visible()
        page.screenshot(path="/tmp/execution-details-mobile.png")
        page.locator("#execution-detail-tab-report").click()
        page.screenshot(path="/tmp/execution-report-mobile.png")
        page.locator("#execution-detail-tab-overview").click()
        page.screenshot(path="/tmp/execution-overview-mobile.png")
        page.locator("#execution-detail-tab-activity").click()
        page.screenshot(path="/tmp/execution-agent-activity-mobile.png")
        page.locator("#execution-detail-tab-logs").click()
        page.screenshot(path="/tmp/execution-technical-logs-mobile.png")
        page.screenshot(path="/tmp/execution-log-detail-mobile.png")
        page.keyboard.press("Escape")
        page.screenshot(path="/tmp/execution-logs-mobile.png", full_page=True)
        page.locator("#execution-logs-type").select_option("case_execution")
        page.locator("#execution-logs-status").select_option("all")
        page.locator("#execution-logs-rows .execution-log-view").first.click()
        page.locator("#execution-detail-tab-cases").click()
        playwright.expect(page.locator("#execution-case-rows tr")).to_have_count(10)
        page.screenshot(path="/tmp/execution-cases-mobile.png")
        page.keyboard.press("Escape")
        page.locator('[data-execution-view="dashboard"]').click()
        playwright.expect(page.locator("#progress-dashboard-view")).to_be_visible()
        page.locator("#bdd-test-results .test-failure-disclosure summary").click()
        playwright.expect(page.locator("#bdd-test-results .test-failure-evidence")).to_contain_text(
            "Expected 200, got 400"
        )
        assert not errors
        browser.close()
