"""Exercise all five tabs and handoffs using deterministic provider responses."""

import copy
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
    if mode == "automation":
        second_story = copy.deepcopy(handoff["stories"]["stories"][0])
        second_story["id"] = "ST-002"
        handoff["stories"]["stories"].append(second_story)
        second_scenario = copy.deepcopy(handoff["scenarios"]["scenarios"][0])
        second_scenario.update(id="SC-002", story_id="ST-002")
        handoff["scenarios"]["scenarios"].append(second_scenario)
    from test_automation_execution_agent import automation_suite

    suite = automation_suite().model_dump(mode="json")
    suite["test_cases"][0]["acceptance_criteria_covered"] = ["ST-001", "SC-001"]
    if mode == "manual":
        suite["test_cases"][0]["execution_mode"] = "manual"
        suite["test_cases"][0]["gherkin"] = None
    errors, calls, pending_stories, cancellations = [], [], [], []
    pending_stages = {}

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
        elif path.endswith("/cancel"):
            cancellations.append(path)
            result = {"cancelled": True}
        elif path == "/api/workflow/requirements/document":
            result = {
                "description": handoff["request"]["description"],
                "filename": "Requirements.pdf",
            }
        elif path == "/api/workflow/stories":
            pending_stories.append(r)
            return
        elif path == "/api/workflow/jira-stories":
            payload = r.request.post_data_json
            assert payload["project_key"] == "TEST"
            assert payload["selected_story_ids"] == ["ST-001"]
            assert payload["approved_by"] == {"ST-001": "Story Reviewer"}
            result = {
                "results": [
                    {
                        "story_id": "ST-001",
                        "status": "created",
                        "issue_key": "TEST-123",
                        "url": "https://jira.example/browse/TEST-123",
                    }
                ]
            }
        elif path == "/api/workflow/scenarios":
            result = handoff["scenarios"]
            assert r.request.post_data_json["stories"] == handoff["stories"]
        elif path in ("/api/workflow/validate-stories", "/api/workflow/validate-scenarios"):
            result = r.request.post_data_json
            if path.endswith("validate-stories") and not result["stories"]["stories"][0]["title"]:
                r.fulfill(
                    status=422, json={"detail": "Story title must contain at least 3 characters"}
                )
                return
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
        if path in (
            "/api/workflow/scenarios",
            "/api/workflow/test-cases",
            "/api/workflow/execution-plan",
            "/api/workflow/execute",
        ):
            pending_stages[path] = (r, result)
            return
        r.fulfill(json=result)

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)

        def stage_popup(button, endpoint, title, *, background=False, cancel=False, fail=False):
            with page.expect_request(lambda request: urlparse(request.url).path == endpoint):
                page.locator(button).click()
            pw.expect(page.locator("#generation-overlay")).to_be_visible()
            pw.expect(page.locator("#generation-overlay-title")).to_have_text(title)
            pw.expect(page.locator("#cancel-generation-overlay")).to_be_visible()
            pw.expect(page.locator("#background-generation-overlay")).to_be_visible()
            request, result = pending_stages.pop(endpoint)
            if background:
                page.locator("#background-generation-overlay").click()
                pw.expect(page.locator("#generation-overlay")).to_be_hidden()
                pw.expect(page.locator("#stop-generation")).to_be_visible()
            if cancel:
                page.locator(
                    "#stop-generation" if background else "#cancel-generation-overlay"
                ).click()
                pw.expect(page.locator("#stage-status")).to_contain_text("cancelled")
                pw.expect(page.locator(button)).to_be_enabled()
                assert (
                    f"/api/generation/{request.request.headers['x-request-id']}/cancel"
                    in cancellations
                )
                request.fulfill(json=result)
            elif fail:
                request.fulfill(status=503, json={"detail": "Stage provider unavailable"})
                pw.expect(page.locator("#stage-status")).to_contain_text(
                    "Stage provider unavailable"
                )
            else:
                request.fulfill(json=result)
            pw.expect(page.locator("#generation-overlay")).to_be_hidden()
            pw.expect(page.locator("#stop-generation")).to_be_hidden()

        page.goto("http://localhost/")
        page.locator("#finance-explore").click()
        pw.expect(page.locator('[data-finance-product="PCP"]')).to_be_focused()
        page.locator('[data-finance-product="BCH"]').focus()
        page.keyboard.press("Enter")
        pw.expect(page.locator("#finance-product-name")).to_have_text("Business Contract Hire")
        pw.expect(page.locator('[data-finance-product="BCH"]')).to_have_attribute(
            "aria-pressed", "true"
        )
        pw.expect(page.locator("#description")).to_have_value("")
        page.locator("#finance-start").click()
        pw.expect(page.locator("#description")).to_be_focused()
        page.locator('[data-finance-product="PCP"]').click()
        pw.expect(page.get_by_role("tab")).to_have_count(0)
        pw.expect(page.locator(".stage-workspace")).to_be_hidden()
        page.screenshot(path="/tmp/workflow-input.png", full_page=True)
        pw.expect(
            page.get_by_role("heading", name="Which finance requirement should we test?")
        ).to_be_visible()
        for control in ("output-target", "manual-testing-type", "llm-model"):
            pw.expect(page.locator(f"#generate-form #{control}")).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        for control in ("output-target", "manual-testing-type", "llm-model"):
            pw.expect(page.locator(f"#{control}")).to_be_visible()
        page.screenshot(path="/tmp/workflow-input-mobile.png", full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator("#output-target").select_option(mode)
        if mode == "automation":
            page.locator("#requirement-file").set_input_files(
                {
                    "name": "Requirements.pdf",
                    "mimeType": "application/pdf",
                    "buffer": b"Browser upload fixture",
                }
            )
            pw.expect(page.locator("#file-name")).to_have_text("Requirements.pdf")
            pw.expect(page.locator("#file-type")).to_have_text("PDF")
            pw.expect(page.locator("#description")).to_have_value("")
        else:
            page.locator("#description").fill(handoff["request"]["description"])
        page.locator("#generate").click()
        pw.expect(page.locator("#status")).to_contain_text("Story Agent")
        pw.expect(page.locator(".stage-workspace")).to_be_hidden()
        page.wait_for_timeout(100)
        assert pending_stories
        assert (
            pending_stories[-1].request.post_data_json["description"]
            == handoff["request"]["description"]
        )
        pw.expect(page.locator("#generation-overlay")).to_be_visible()
        pw.expect(page.locator("#generation-overlay-title")).to_contain_text("Generating stories")
        pw.expect(page.locator("#background-generation-overlay")).to_be_visible()
        pw.expect(page.locator("#generate")).to_be_disabled()
        pending_stories.pop().fulfill(status=503, json={"detail": "Story provider unavailable"})
        pw.expect(page.locator("#status")).to_contain_text("Story provider unavailable")
        pw.expect(page.locator(".stage-workspace")).to_be_hidden()
        pw.expect(page.locator("#generation-overlay")).to_be_hidden()
        page.locator("#generate").click()
        pw.expect(page.locator("#status")).to_contain_text("Story Agent")
        page.wait_for_timeout(100)
        cancelled_request = pending_stories.pop()
        request_id = cancelled_request.request.headers["x-request-id"]
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path="/tmp/story-generation-popup.png", full_page=True)
        if mode == "automation":
            page.locator("#background-generation-overlay").click()
            page.locator("#stop-generation").click()
        else:
            page.locator("#cancel-generation-overlay").click()
        pw.expect(page.locator("#status")).to_contain_text("Story generation cancelled")
        pw.expect(page.locator("#generate")).to_be_enabled()
        assert f"/api/generation/{request_id}/cancel" in cancellations
        cancelled_request.fulfill(json=handoff["stories"])
        pw.expect(page.locator(".stage-workspace")).to_be_hidden()
        pw.expect(page.locator("#generation-overlay")).to_be_hidden()
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator("#generate").click()
        pw.expect(page.locator("#status")).to_contain_text("Story Agent")
        page.wait_for_timeout(100)
        page.locator("#background-generation-overlay").click()
        pw.expect(page.locator("#generation-overlay")).to_be_hidden()
        pw.expect(page.locator("#stop-generation")).to_be_visible()
        pw.expect(page.locator("#generate")).to_be_disabled()
        pw.expect(page.locator("#status")).to_contain_text("background")
        pw.expect(page.locator(".stage-workspace")).to_be_hidden()
        pending_stories.pop().fulfill(json=handoff["stories"])
        pw.expect(page.locator("#stage-panel-2")).to_be_visible()
        if mode == "automation":
            pw.expect(page.locator("#description")).to_have_value("")
            pw.expect(page.locator("#file-preview")).to_be_visible()
            pw.expect(page.locator("#file-name")).to_have_text("Requirements.pdf")
            pw.expect(page.locator("#file-type")).to_have_text("PDF")
            pw.expect(page.locator("#character-count")).to_have_text("0 characters")
        else:
            pw.expect(page.locator("#description")).to_have_value(handoff["request"]["description"])
        pw.expect(page.get_by_role("tab")).to_have_count(5)
        assert page.locator(".stage-tabs").bounding_box()["y"] >= (
            page.locator(".studio-layout").bounding_box()["y"]
            + page.locator(".studio-layout").bounding_box()["height"]
        )
        page.locator("#stage-tab-1").focus()
        page.keyboard.press("ArrowRight")
        pw.expect(page.locator("#stage-tab-2")).to_be_focused()
        pw.expect(page.locator("#story-cards")).to_contain_text("ST-001")
        pw.expect(page.locator("#stage-status")).to_contain_text("Stories ready")
        first_story = page.locator('[data-story-index="0"]')
        pw.expect(page.locator("#stage-stories")).to_be_disabled()
        pw.expect(page.locator("#story-jira-open")).to_be_disabled()
        pw.expect(page.locator("#review-stories")).to_be_disabled()
        page.locator("#select-all-stories").uncheck()
        pw.expect(page.locator("#accept-selected-stories")).to_be_disabled()
        page.locator("#select-all-stories").check()
        page.locator("#accept-selected-stories").click()
        pw.expect(page.locator("#story-reviewer-error")).to_be_visible()
        pw.expect(page.locator("#stories-accepted-by")).to_be_focused()
        pw.expect(first_story.locator(".story-review-state")).to_have_text("Review required")
        page.locator("#stories-accepted-by").fill(" ")
        first_story.locator(".story-accept").click()
        pw.expect(page.locator("#story-reviewer-error")).to_be_visible()
        page.locator("#stories-accepted-by").fill("Story Reviewer")
        if mode == "automation":
            first_story.locator(".story-check").uncheck()
            assert page.locator("#select-all-stories").evaluate("el => el.indeterminate")
            pw.expect(page.locator("#story-selection-count")).to_have_text("1 selected")
            page.locator("#select-all-stories").check()
            page.locator("#accept-selected-stories").click()
            pw.expect(page.locator('[data-story-index="1"] .story-edit-status')).to_contain_text(
                "accepted by Story Reviewer"
            )
        else:
            first_story.locator(".story-accept").click()
        pw.expect(first_story.locator(".story-review-state")).to_have_text("Accepted")
        pw.expect(first_story.locator(".story-edit-status")).to_contain_text(
            "accepted by Story Reviewer"
        )
        pw.expect(page.locator("#accept-selected-stories")).to_be_disabled()
        pw.expect(page.locator("#review-stories")).to_be_enabled()
        pw.expect(page.locator("#stage-stories")).to_be_disabled()
        pw.expect(page.locator("#stage-stories")).to_have_attribute(
            "title",
            "Stories are already created. Change the requirements to create new stories.",
        )
        page.locator("#select-all-stories").uncheck()
        first_story.locator(".story-check").check()
        pw.expect(page.locator("#story-jira-open")).to_be_enabled()
        page.locator("#story-jira-open").click()
        pw.expect(page.locator("#story-jira-selection")).to_have_text(
            "1 selected approved stories to create."
        )
        page.locator("#story-jira-create").click()
        pw.expect(page.locator("#story-jira-status")).to_contain_text("valid project key")
        page.locator("#story-jira-project").fill("TEST")
        page.locator("#story-jira-create").click()
        pw.expect(page.locator("#story-jira-results")).to_contain_text("TEST-123")
        pw.expect(page.locator("#story-jira-create")).to_be_disabled()
        page.locator("#story-jira-close").click()
        pw.expect(page.locator("#story-jira-open")).to_be_disabled()
        first_story.locator(".story-open-edit").click()
        pw.expect(first_story.get_by_role("dialog")).to_be_visible()
        pw.expect(first_story.get_by_role("button", name="Update", exact=True)).to_be_visible()
        pw.expect(first_story.get_by_role("button", name="Discard", exact=True)).to_be_visible()
        first_story.locator('[data-field="title"]').fill("")
        pw.expect(first_story.locator(".story-check")).to_be_disabled()
        pw.expect(page.locator("#accept-selected-stories")).to_be_disabled()
        pw.expect(first_story.locator(".story-accept")).to_be_disabled()
        pw.expect(page.locator("#review-stories")).to_be_disabled()
        first_story.locator(".story-save").click()
        pw.expect(first_story.locator(".story-dialog-status")).to_contain_text("at least 3")
        pw.expect(first_story.locator(".story-edit")).to_be_visible()
        pw.expect(first_story.locator(".story-accept")).to_be_disabled()
        first_story.locator('[data-field="title"]').fill("Review the supplied requirements")
        first_story.locator(".story-save").click()
        pw.expect(page.locator("#stage-status")).to_contain_text("ST-001 changes saved")
        pw.expect(first_story.locator("h3")).to_have_text("Review the supplied requirements")
        pw.expect(first_story.get_by_role("dialog")).not_to_be_visible()
        pw.expect(page.locator("#review-stories")).to_be_disabled()
        if mode == "automation":
            pw.expect(page.locator('[data-story-index="1"] .story-review-state')).to_have_text(
                "Accepted"
            )
        first_story.locator(".story-accept").click()
        pw.expect(page.locator("#review-stories")).to_be_enabled()
        handoff["stories"]["stories"][0]["title"] = "Review the supplied requirements"
        page.locator("#review-stories").click()
        stage_popup(
            "#stage-scenarios", "/api/workflow/scenarios", "Generating test scenarios", cancel=True
        )
        pw.expect(page.locator("#review-scenarios")).to_be_disabled()
        stage_popup(
            "#stage-scenarios",
            "/api/workflow/scenarios",
            "Generating test scenarios",
            background=True,
        )
        pw.expect(page.locator("#scenario-cards")).to_contain_text("SC-001")
        pw.expect(page.locator("#stage-status")).to_contain_text("Scenarios ready")
        first_scenario = page.locator('[data-scenario-index="0"]')
        first_scenario.locator(".scenario-open-edit").click()
        pw.expect(first_scenario.get_by_role("dialog")).to_be_visible()
        first_scenario.locator('[data-field="title"]').fill("Discard this draft")
        first_scenario.locator(".scenario-discard").click()
        pw.expect(first_scenario.get_by_role("dialog")).not_to_be_visible()
        pw.expect(first_scenario.locator("h3")).to_have_text("Read the supplied source")
        first_scenario.locator(".scenario-open-edit").click()
        first_scenario.locator('[data-field="title"]').fill("Updated scenario title")
        pw.expect(page.locator("#review-scenarios")).to_be_disabled()
        first_scenario.locator(".scenario-update").click()
        pw.expect(page.locator("#stage-status")).to_contain_text("Scenario updated")
        first_scenario = page.locator('[data-scenario-index="0"]')
        pw.expect(first_scenario.locator("h3")).to_have_text("Updated scenario title")
        handoff["scenarios"]["scenarios"][0]["title"] = "Updated scenario title"
        pw.expect(page.locator("#review-scenarios")).to_be_disabled()
        page.locator("#accept-scenarios").click()
        pw.expect(page.locator("#scenario-reviewer-error")).to_be_visible()
        pw.expect(page.locator("#scenarios-accepted-by")).to_be_focused()
        page.locator("#scenarios-accepted-by").fill("Scenario Reviewer")
        page.locator("#accept-scenarios").click()
        pw.expect(first_scenario.locator(".scenario-review-state")).to_have_text(
            "Approved by Scenario Reviewer"
        )
        pw.expect(page.locator("#review-scenarios")).to_be_enabled()
        page.locator("#review-scenarios").click()
        stage_popup("#stage-cases", "/api/workflow/test-cases", "Generating test cases", fail=True)
        pw.expect(page.locator("#review-cases")).to_be_disabled()
        stage_popup("#stage-cases", "/api/workflow/test-cases", "Generating test cases")
        pw.expect(page.locator("#results")).to_be_visible()
        for control in (
            "automation-language",
            "suite-view-menu",
            "accepted-by",
            "accept-selected",
            "suite-download-menu",
        ):
            pw.expect(page.locator(f"#{control}")).to_be_visible()
        page.locator(".suite-jira summary").click()
        pw.expect(page.locator("#jira-key")).to_be_visible()
        pw.expect(page.locator("#jira")).to_be_visible()
        page.locator(".suite-jira summary").click()
        assert calls[0]["request"]["generation_target"] == mode
        assert calls[0]["request"]["description"] == handoff["request"]["description"]
        assert calls[0]["stories"] == handoff["stories"]
        assert calls[0]["scenarios"] == handoff["scenarios"]
        if mode == "automation":
            stage_popup(
                "#review-cases", "/api/workflow/execution-plan", "Preparing the execution plan"
            )
            pw.expect(page.locator("#stage-execution-list")).to_contain_text("generated.feature")
            page.locator("#stage-tab-4").click()
            stage_popup(
                "#stage-tab-5",
                "/api/workflow/execution-plan",
                "Preparing the execution plan",
                fail=True,
            )
            pw.expect(page.locator("#stage-run")).to_be_disabled()
            page.locator("#stage-tab-4").click()
            stage_popup(
                "#stage-tab-5", "/api/workflow/execution-plan", "Preparing the execution plan"
            )
            pw.expect(page.locator("#stage-run")).to_be_enabled()
            stage_popup(
                "#stage-run",
                "/api/workflow/execute",
                "Running test execution",
                background=True,
                cancel=True,
            )
            pw.expect(page.locator("#stage-execution-results")).to_be_empty()
            stage_popup(
                "#stage-run", "/api/workflow/execute", "Running test execution", background=True
            )
            pw.expect(page.locator("#stage-execution-results")).to_contain_text("HealthIsAvailable")
            pw.expect(page.locator("#stage-execution-results")).to_contain_text("Passed")
        else:
            page.locator("#review-cases").click()
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
        first_story.locator(".story-open-edit").click()
        first_story.locator('[data-field="title"]').fill("Unaccepted draft change")
        assert page.evaluate("suite") is not None
        first_story.locator(".story-cancel-edit").click()
        pw.expect(first_story.get_by_role("dialog")).not_to_be_visible()
        assert page.evaluate("suite") is not None
        pw.expect(first_story.locator("h3")).to_have_text("Review the supplied requirements")
        pw.expect(first_story.locator(".story-review-state")).to_have_text("Accepted")
        pw.expect(page.locator("#review-stories")).to_be_enabled()
        first_story.locator(".story-open-edit").click()
        first_story.locator('[data-field="title"]').fill("Discard with Escape")
        page.keyboard.press("Escape")
        pw.expect(first_story.get_by_role("dialog")).not_to_be_visible()
        pw.expect(first_story.locator(".story-open-edit")).to_be_focused()
        pw.expect(first_story.locator("h3")).to_have_text("Review the supplied requirements")
        page.locator("#stage-tab-1").click()
        page.locator("#description").fill("Changed requirement: read a different BRD document")
        pw.expect(page.locator(".stage-workspace")).to_be_hidden()
        pw.expect(page.locator("#generate")).to_be_visible()
        pw.expect(page.locator("#stage-run")).to_be_disabled()
        pw.expect(page.locator("#stage-execution-results")).to_be_empty()
        assert page.evaluate("suite") is None
        assert not errors
        browser.close()
