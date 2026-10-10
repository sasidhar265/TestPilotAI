"""BA document review is visible within Requirements and safe to render."""

import os
from urllib.parse import urlparse

import pytest
from test_business_analyst import assessment
from test_mobile_navigation_browser import mobile_route


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_ba_review_upload_summary_and_source_invalidation():
    pw = pytest.importorskip("playwright.sync_api")
    errors, requests, pending_reviews = [], [], []
    report = assessment().model_dump() | {
        "assessed_at": "2026-10-09T10:00:00Z",
        "document_fingerprint": "a" * 64,
        "knowledge_fingerprint": "b" * 64,
        "knowledge_sources": [],
        "knowledge_limitations": ["No effective approved business sources available."],
        "business_approval": "not_granted",
        "regulatory_compliance": "not_assessed",
        "outcome": "needs_clarification",
        "summary": "<img src=x onerror=alert(1)> Document review summary.",
    }

    def route(request):
        path = urlparse(request.request.url).path
        if path == "/api/workflow/ba-review":
            requests.append(request.request.post_data_json)
            pending_reviews.append(request)
        elif path == "/api/workflow/requirements/document":
            request.fulfill(
                json={
                    "description": "Uploaded BRD describes quotation deposit validation.",
                    "uploaded_brd_receipt": "server-receipt",
                    "filename": "BRD.txt",
                }
            )
        elif path.startswith("/api/generation/") and path.endswith("/events"):
            request.fulfill(
                json={
                    "events": [
                        {
                            "sequence": 1,
                            "timestamp": "2026-10-09T10:00:00Z",
                            "agent": "BA Agent review",
                            "status": "success",
                                "action": "ba_review_knowledge",
                            "summary": "Reviewed BRD scope and domain knowledge <img src=x>.",
                        }
                    ]
                    if requests
                    else [],
                    "complete": bool(requests),
                }
            )
        else:
            mobile_route(request)

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://localhost/")
        assert page.get_by_role("link", name="BA Agent", exact=True).count() == 0
        pw.expect(page.locator("h1")).to_have_text("Requirements")
        pw.expect(page.locator("#ba-review")).to_be_visible()
        workflow = page.locator(".agent-route-card")
        pw.expect(workflow).to_contain_text("Review BRD")
        pw.expect(workflow).not_to_contain_text("ManualTestCaseGeneratorAgent")
        actions = page.locator("#test-studio .generation-actions > button:visible").evaluate_all(
            "elements => elements.map(element => { const r = element.getBoundingClientRect(); "
            "return {top: r.top, height: r.height}; })"
        )
        tops = [action["top"] for action in actions]
        assert max(tops) - min(tops) < 1
        assert all(action["height"] >= 44 for action in actions)
        page.locator("#requirement-file").set_input_files(
            {"name": "BRD.txt", "mimeType": "text/plain", "buffer": b"Quotation deposit validation"}
        )
        page.click("#ba-review")
        pw.expect(page.locator("#generation-overlay")).to_be_visible()
        pw.expect(page.locator("#generation-background-events li")).to_have_count(1)
        page.click("#background-generation-overlay")
        tray = page.locator("#background-run-tray")
        pw.expect(tray).to_be_visible()
        pw.expect(page.locator("#background-run-title")).to_have_text("BA review")
        pw.expect(page.locator("#background-run-percent")).to_have_text("40%")
        pw.expect(page.locator("#reopen-generation")).to_have_text("Open")
        pw.expect(page.locator("#background-run-body")).to_be_hidden()
        assert tray.evaluate("element => getComputedStyle(element).position") == "fixed"
        pw.expect(page.locator("#background-run-time")).not_to_have_text("00:00 elapsed")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        bounds = tray.bounding_box()
        assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
        assert 844 - bounds["y"] - bounds["height"] >= 15
        page.screenshot(path="/private/tmp/ba-review-banner-mobile.png", full_page=True)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.evaluate(
            "window.recordedProgressNode = "
            "document.querySelector('#generation-background-events li')"
        )
        page.evaluate("window.navigateWorkspace('/progress')")
        pw.expect(tray).to_be_visible()
        page.click("#reopen-generation")
        pw.expect(page.locator("#generation-overlay")).to_be_visible()
        pw.expect(page.locator("#generation-overlay-time")).not_to_have_text("00:00 elapsed")
        assert page.evaluate(
            "window.recordedProgressNode === "
            "document.querySelector('#generation-background-events li')"
        )
        assert len(requests) == 1
        page.click("#background-generation-overlay")
        page.evaluate("window.navigateWorkspace('/')")
        pending_reviews.pop().fulfill(json=report)
        pw.expect(page.locator("#ba-report")).to_be_visible()
        pw.expect(tray).to_contain_text("Operation completed")
        pw.expect(page.locator("#background-run-percent")).to_have_text("100%")
        pw.expect(tray).to_have_attribute("data-status", "completed")
        completed_time = page.locator("#background-run-time").inner_text()
        page.click("#reopen-generation")
        pw.expect(page.locator("#generation-overlay-title")).to_have_text("BA review · Completed")
        pw.expect(page.locator("#cancel-generation-overlay")).to_be_hidden()
        pw.expect(page.locator("#generation-overlay-time")).to_have_text(completed_time)
        pw.expect(page.locator("#generation-background-events li")).to_have_count(1)
        page.click("#background-generation-overlay")
        page.click("#dismiss-generation-progress")
        pw.expect(tray).to_be_hidden()
        pw.expect(workflow.locator(".agent-route-badge")).to_have_text("Completed")
        pw.expect(workflow).to_contain_text("BA Agent review")
        pw.expect(workflow.locator(".agent-route-step")).to_have_count(1)
        pw.expect(workflow.locator("time")).to_have_attribute("datetime", "2026-10-09T10:00:00Z")
        assert workflow.locator("img").count() == 0
        pw.expect(page.locator("#ba-report")).to_contain_text("needs clarification")
        pw.expect(page.locator(".ba-area-grid article")).to_have_count(8)
        assert requests[0]["uploaded_brd_receipt"] == "server-receipt"
        assert "Uploaded BRD" in requests[0]["description"]
        assert page.locator("#ba-report img").count() == 0
        page.fill("#description", "Changed business requirements for a new document.")
        pw.expect(page.locator("#ba-report")).to_be_hidden()
        pw.expect(workflow.locator(".agent-route-badge")).to_have_text("Ready")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        mobile_buttons = page.locator("#test-studio .generation-actions > button:visible")
        mobile_actions = mobile_buttons.evaluate_all(
            "elements => elements.map(element => { const r = element.getBoundingClientRect(); "
            "return {left: r.left, width: r.width, top: r.top}; })"
        )
        assert len({round(action["left"]) for action in mobile_actions}) == 1
        assert len({round(action["width"]) for action in mobile_actions}) == 1
        assert mobile_actions[0]["top"] < mobile_actions[1]["top"]
        page.locator("#file-remove").click()
        requests.clear()
        page.fill("#description", "")
        page.click("#ba-review")
        pw.expect(workflow.locator(".agent-route-badge")).to_have_text("Failed")
        pw.expect(workflow.locator(".agent-route-step")).to_have_count(0)
        pw.expect(page.locator("#ba-status")).to_contain_text("at least 10 characters")
        assert not errors, errors
        browser.close()
