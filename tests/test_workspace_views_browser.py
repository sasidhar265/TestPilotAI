"""Focused UI views retain drafts and reuse the existing suite actions."""

import os

import pytest
from test_automation_execution_agent import automation_suite
from test_mobile_navigation_browser import mobile_route


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_focused_views_history_and_automation_preview():
    pw = pytest.importorskip("playwright.sync_api")
    errors = []

    def route(request):
        if request.request.url.endswith("/api/context-converter/feature"):
            request.fulfill(
                body="Feature: Existing suite\n  Scenario: Health is available\n",
                content_type="text/plain",
            )
        elif request.request.url.endswith("/api/auth/profile"):
            request.fulfill(
                json={
                    "username": "reviewer",
                    "display_name": "Reviewer",
                    "initials": "RE",
                    "is_admin": True,
                }
            )
        else:
            mobile_route(request)

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://localhost/?view=automation")
        pw.expect(page.locator("h1")).to_have_text("Automation packs")
        pw.expect(page.locator("#stage-tab-6")).to_be_visible()
        pw.expect(page.locator("#stage-tab-6")).to_have_attribute("aria-selected", "true")
        pw.expect(page.locator('[data-suite-action="view-feature"]')).to_be_disabled()
        pw.expect(page.locator(".studio-layout")).to_be_hidden()
        page.get_by_role("link", name="Requirements", exact=True).click()
        pw.expect(page.locator(".finance-hero")).to_be_visible()
        pw.expect(page.locator(".finance-hero")).to_contain_text("AUTOMOBILE FINANCE INTELLIGENCE")
        pw.expect(page.locator(".finance-explorer")).to_be_hidden()
        page.click("#finance-explore")
        pw.expect(page).to_have_url("http://localhost/auto-finance-guide?section=products")
        pw.expect(
            page.frame_locator("#auto-finance-guide-frame").locator("#products")
        ).to_be_visible()
        pw.expect(page.locator('#finance-navigation a[href="/products"]')).to_have_count(0)
        pw.expect(page.locator(".workflow-shortcuts")).to_have_count(0)
        pw.expect(page.locator(".workflow-home-link")).to_have_count(0)
        page.get_by_role("link", name="Requirements", exact=True).click()
        pw.expect(page.locator(".finance-domain-selection")).to_be_hidden()
        pw.expect(page.locator(".finance-guide")).to_be_hidden()
        pw.expect(page.locator("#finance-reference-status")).to_be_hidden()
        draft = "Verify the supplied vehicle finance requirements without changing their content."
        page.fill("#description", draft)
        page.get_by_role("link", name="Stories", exact=True).click()
        pw.expect(page.locator("h1")).to_have_text("Stories")
        pw.expect(page.locator("#stage-panel-2")).to_be_visible()
        pw.expect(page.locator("#stage-stories")).to_be_disabled()
        page.go_back()
        pw.expect(page.locator("h1")).to_have_text("Requirements")
        pw.expect(page.locator("#description")).to_have_value(draft)
        page.go_forward()
        pw.expect(page.locator("h1")).to_have_text("Stories")
        finance_navigation = page.locator(".nav-parent", has_text="Auto finance")
        if finance_navigation.get_attribute("aria-expanded") == "false":
            finance_navigation.click()
        page.get_by_role("link", name="UK finance guide", exact=True).click()
        guide = page.frame_locator("#auto-finance-guide-frame")
        guide.locator("#product-audience").select_option("business")
        pw.expect(guide.locator("#product-cards .card:visible")).to_have_count(9)
        page.get_by_role("link", name="Requirements", exact=True).click()
        page.locator(".finance-context-settings summary").click()
        pw.expect(page.locator(".finance-domain-selection")).to_be_visible()
        pw.expect(page.locator("#description")).to_have_value(draft)
        page.evaluate(
            "data => { validationReport = {passed: true}; render(data); }",
            automation_suite().model_dump(mode="json"),
        )
        pw.expect(page.locator("h1")).to_have_text("Test cases")
        page.get_by_role("link", name="Automation packs", exact=True).click()
        pw.expect(page.locator("#cases")).to_be_hidden()
        page.locator('[data-suite-action="view-feature"]').click()
        pw.expect(page.locator("#feature-file-view")).to_be_visible()
        pw.expect(page.locator("#feature-file-content")).to_contain_text("Existing suite")
        page.get_by_role("link", name="Test cases", exact=True).click()
        page.locator("#suite-view-menu summary").click()
        page.locator("#view-feature").click()
        pw.expect(page.locator("h1")).to_have_text("Automation packs")
        pw.expect(page.locator("#feature-file-view")).to_be_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("tab", name="Automation packs", exact=False).focus()
        page.keyboard.press("Home")
        pw.expect(page.locator("#stage-tab-1")).to_be_focused()
        page.keyboard.press("ArrowLeft")
        pw.expect(page.locator("#stage-tab-6")).to_be_focused()
        pw.expect(page.locator("h1")).to_have_text("Automation packs")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.get_by_role("tab", name="Execution", exact=False).click()
        pw.expect(page.locator("#stage-panel-5")).to_be_visible()
        pw.expect(page.locator("#work-dashboard")).to_be_hidden()
        page.locator('.primary-nav a[href="/progress"]').click()
        pw.expect(page.locator("#work-dashboard")).to_be_visible()
        pw.expect(page.locator("#stage-panel-5")).to_be_hidden()
        pw.expect(page.locator(".workflow-support-navigation")).to_have_count(0)
        page.reload()
        pw.expect(page.locator("#work-dashboard")).to_be_visible()
        page.get_by_role("button", name="Quality workspace", exact=True).click()
        page.get_by_role("link", name="Test cases", exact=True).click()
        assert not errors, errors
        pw.expect(page.locator("#results")).to_be_visible()
        pw.expect(page.locator("#cases .case")).to_have_count(len(automation_suite().test_cases))
        page.get_by_role("link", name="Requirements", exact=True).click()
        pw.expect(page.locator("#description")).to_have_value(draft)
        assert not errors, errors
        browser.close()
