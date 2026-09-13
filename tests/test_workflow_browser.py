"""Exercise all five tabs and handoffs using deterministic provider responses."""

import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("mode", ["manual", "automation"])
def test_five_stage_workflow_and_source_invalidation(mode):
    pw = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    fixture = json.loads(Path("automation/Input/Workflow.Json").read_text())
    handoff = fixture["approved-scenarios"]["body"]
    from test_automation_execution_agent import automation_suite

    suite = automation_suite().model_dump(mode="json")
    suite["test_cases"][0]["acceptance_criteria_covered"] = ["ST-001", "SC-001"]
    if mode == "manual":
        suite["test_cases"][0]["execution_mode"] = "manual"
        suite["test_cases"][0]["gherkin"] = None
    errors, calls = [], []

    def route(r):
        path = urlparse(r.request.url).path
        if path == "/" or path.startswith("/static/"):
            file = static / ("index.html" if path == "/" else path.removeprefix("/static/"))
            r.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
            return
        result = {"ok": True, "events": [], "complete": True, "models": []}
        if path == "/api/workspace/rules":
            result = {"business_rules": []}
        elif path == "/api/auth/profile":
            result = {"display_name": "Reviewer", "is_admin": False}
        elif path == "/api/workflow/stories":
            result = handoff["stories"]
        elif path == "/api/workflow/scenarios":
            result = handoff["scenarios"]
            assert r.request.post_data_json["stories"] == handoff["stories"]
        elif path in ("/api/workflow/validate-stories", "/api/workflow/validate-scenarios"):
            result = r.request.post_data_json
        elif path == "/api/workflow/test-cases":
            calls.append(r.request.post_data_json)
            result = {
                "suite": suite,
                "validation": {"passed": True, "score": 100},
                "source_request": r.request.post_data_json["request"],
            }
        elif path == "/api/workflow/execution-plan":
            result = {
                "ready": True,
                "reason": "Configured feature project",
                "cases": [
                    {
                        "feature_file": "Features/generated.feature",
                        "scenario": "Health is available",
                    }
                ],
            }
        elif path == "/api/execution":
            result = {
                "results": r.request.post_data_json["results"],
                "passed": 1,
                "failed": 0,
                "blocked": 0,
                "total": 1,
                "not_run": 0,
                "pass_rate": 100,
            }
        elif path == "/api/workflow/execute":
            result = {
                "status": "passed",
                "passed": 1,
                "failed": 0,
                "skipped": 0,
                "test_results": [{"name": "HealthIsAvailable", "status": "Passed"}],
            }
        r.fulfill(json=result)

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://localhost/")
        pw.expect(page.get_by_role("tab")).to_have_count(5)
        page.locator("#stage-tab-1").focus()
        page.keyboard.press("ArrowRight")
        pw.expect(page.locator("#stage-tab-2")).to_be_focused()
        pw.expect(page.locator("#stage-stories")).to_be_disabled()
        page.locator("#stage-tab-1").click()
        page.screenshot(path="/tmp/workflow-input.png", full_page=True)
        page.locator("#description").fill(handoff["request"]["description"])
        page.locator("#generate").click()
        pw.expect(page.locator("#stage-panel-2")).to_be_visible()
        page.locator("#stage-stories").click()
        pw.expect(page.locator("#story-cards")).to_contain_text("ST-001")
        pw.expect(page.locator("#stage-status")).to_contain_text("Stories ready")
        page.locator("#story-edit summary").click()
        page.locator('#story-editor [data-field="title"]').fill("Read source requirements")
        page.locator("#save-stories").click()
        pw.expect(page.locator("#stage-status")).to_contain_text("Story edits applied")
        page.locator("#review-stories").click()
        page.locator("#stage-scenarios").click()
        pw.expect(page.locator("#scenario-cards")).to_contain_text("SC-001")
        pw.expect(page.locator("#stage-status")).to_contain_text("Scenarios ready")
        page.locator("#review-scenarios").click()
        page.locator("#output-target").select_option(mode)
        page.locator("#stage-cases").click()
        pw.expect(page.locator("#results")).to_be_visible()
        assert calls[0]["stories"] == handoff["stories"]
        assert calls[0]["scenarios"] == handoff["scenarios"]
        page.locator("#review-cases").click()
        if mode == "automation":
            pw.expect(page.locator("#stage-execution-list")).to_contain_text("generated.feature")
            page.locator("#stage-run").click()
            pw.expect(page.locator("#stage-execution-results")).to_contain_text("HealthIsAvailable")
            pw.expect(page.locator("#stage-execution-results")).to_contain_text("Passed")
        else:
            pw.expect(page.locator("#stage-run")).to_be_disabled()
            page.locator(".stage-manual-row select").select_option("passed")
            page.locator(".stage-manual-row textarea").fill("Observed HTTP 200 in test environment")
            page.locator("#save-stage-manual").click()
            pw.expect(page.locator("#stage-status")).to_contain_text(
                "Manual results saved: 1 passed"
            )
        page.locator("#stage-tab-2").click()
        page.screenshot(path="/tmp/workflow-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path="/tmp/workflow-mobile.png", full_page=True)
        page.evaluate("document.documentElement.dataset.theme='dark'")
        page.screenshot(path="/tmp/workflow-dark.png", full_page=True)
        page.locator("#stage-tab-1").click()
        page.locator("#description").fill("Changed requirement: read a different BRD document")
        page.locator("#stage-tab-5").click()
        pw.expect(page.locator("#stage-run")).to_be_disabled()
        pw.expect(page.locator("#stage-execution-results")).to_be_empty()
        assert page.evaluate("suite") is None
        assert not errors
        browser.close()
