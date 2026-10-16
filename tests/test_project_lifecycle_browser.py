"""Live browser journey against an explicitly configured isolated validation server."""

import os
from uuid import uuid4

import pytest


@pytest.mark.skipif(not os.getenv("LIFECYCLE_BROWSER_BASE_URL"), reason="Isolated server required")
def test_human_lifecycle_evidence_rework_and_persistence():
    pw = pytest.importorskip("playwright.sync_api")
    base = os.environ["LIFECYCLE_BROWSER_BASE_URL"]
    with pw.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/login")
        page.locator('[name="username"]').fill(os.environ["ROLE_TEST_ADMIN_USER"])
        page.locator('[name="password"]').fill(os.environ["ROLE_TEST_ADMIN_PASSWORD"])
        page.locator('#login-form button[type="submit"]').click()
        page.wait_for_url(base + "/sdlc")
        project_name = "Browser lifecycle " + uuid4().hex[:8]
        page.locator("#sdlc-name").fill(project_name)
        page.locator("#sdlc-create").get_by_role("button", name="Create project").click()
        page.wait_for_function("() => document.querySelector('#sdlc-project').value !== ''")
        page.locator("#description").fill(
            "Synthetic browser requirements for a governed project lifecycle."
        )
        page.locator("#sdlc-save-requirements").click()
        page.wait_for_function(
            "() => document.querySelector('#sdlc-requirements-status').textContent"
            ".includes('v1 saved')"
        )
        page.goto(base + "/sdlc")
        page.wait_for_function(
            "() => document.querySelector('#lifecycle-status').textContent"
            ".includes('Requirements analysis')"
        )
        assert page.locator('#sdlc-phase-tabs [role="tab"]').count() == 8
        assert page.locator('#sdlc-phase-tabs [aria-current="step"]').inner_text().startswith("01")
        page.locator("#sdlc-next-step").click()
        assert page.locator("#sdlc-step-heading").inner_text() == "Business approval"
        assert page.locator(".lifecycle-action-grid").is_hidden()
        assert page.locator("#lifecycle-status").inner_text().startswith("Requirements analysis")
        page.reload()
        page.locator("#sdlc-current-step").wait_for(state="visible")
        assert page.locator("#sdlc-step-heading").inner_text() == "Business approval"
        page.locator("#sdlc-current-step").click()
        assert page.locator(".lifecycle-action-grid").is_visible()
        evidence = page.locator("#lifecycle-evidence")
        evidence.locator('[name="reference"]').fill("browser-fixture://analysis")
        evidence.locator('[name="comment"]').fill(
            "Synthetic human browser evidence, not a real AI analysis"
        )
        evidence.get_by_role("button", name="Record evidence").click()
        decision = page.locator("#lifecycle-decision")
        page.wait_for_function(
            "() => !document.querySelector('#lifecycle-decision [value=approved]').disabled"
        )
        decision.locator('[name="comment"]').fill("Synthetic review for browser validation")
        decision.get_by_role("button", name="Complete stage").click()
        page.wait_for_function(
            "() => document.querySelector('#lifecycle-status').textContent"
            ".includes('Business analyst validation')"
        )
        page.reload()
        page.wait_for_function(
            "() => document.querySelector('#lifecycle-status').textContent"
            ".includes('Business analyst validation')"
        )
        evidence.locator('[name="reference"]').fill("browser-fixture://ba-validation")
        evidence.locator('[name="comment"]').fill("Synthetic BA validation evidence")
        evidence.get_by_role("button", name="Record evidence").click()
        page.wait_for_function(
            "() => !document.querySelector('#lifecycle-decision [value=approved]').disabled"
        )
        decision.locator('[name="comment"]').fill("Synthetic BA handoff for browser verification")
        decision.get_by_role("button", name="Complete stage").click()
        page.wait_for_function(
            "() => document.querySelector('#sdlc-step-heading').textContent === 'Business approval'"
        )
        assert "phase=business-approval" in page.url
        page.reload()
        page.wait_for_function(
            "() => document.querySelector('#sdlc-step-heading').textContent === 'Business approval'"
        )
        decision.locator('[name="comment"]').fill(
            "Resolve the documented clarification before approval"
        )
        decision.get_by_role("button", name="Request rework").click()
        page.wait_for_function(
            "() => document.querySelector('#lifecycle-status').textContent"
            ".includes('Clarification')"
        )
        records_panel = page.locator("#lifecycle-records-summary").locator("..")
        if records_panel.get_attribute("open") is None:
            page.locator("#lifecycle-records-summary").click()
        form = page.locator("#lifecycle-item-form")
        form.locator('[name="title"]').fill("Draft record to preserve")
        page.locator("#sdlc-phase-requirements").click()
        assert form.locator('[name="title"]').input_value() == "Draft record to preserve"
        page.locator("#sdlc-step-links").get_by_role(
            "link", name="Review business analysis"
        ).click()
        assert form.locator('[name="title"]').input_value() == "Draft record to preserve"
        assert "stage=" not in page.url
        page.locator("#sdlc-phase-backlog").click()
        assert page.locator("#sdlc-step-heading").inner_text() == "Requirements"
        assert form.locator('[name="title"]').input_value() == "Draft record to preserve"
        page.locator("#lifecycle-clear-draft").click()
        form.locator('[name="title"]').fill("Synthetic linked requirement")
        form.get_by_role("button", name="Save changes").click()
        page.wait_for_function(
            "() => document.querySelector('#lifecycle-work-items').textContent"
            ".includes('Synthetic linked requirement')"
        )
        page.reload()
        page.wait_for_function(
            "() => document.querySelector('#lifecycle-work-items').textContent"
            ".includes('Synthetic linked requirement')"
        )
        page.goto(base + "/project-dashboard")
        queue = page.locator("#lifecycle-queue")
        queue.get_by_role("link").filter(has_text=project_name).wait_for()
        assert (
            "requirements analysis"
            in queue.get_by_role("link").filter(has_text=project_name).inner_text()
        )
        queue.get_by_role("link").filter(has_text=project_name).click()
        page.wait_for_url(base + "/sdlc")
        page.wait_for_function(
            "() => document.querySelector('#lifecycle-status').textContent"
            ".includes('Requirements analysis')"
        )
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.locator("#project-lifecycle").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path="/tmp/qls-lifecycle-mobile.png", full_page=True)
        assert not errors
        browser.close()
