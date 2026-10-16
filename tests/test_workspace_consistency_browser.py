"""Shared presentation contracts across actual page assets and responsive layouts."""

import os

import pytest
from test_mobile_navigation_browser import mobile_route


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize(
    "name", ["index", "documentation", "knowledge", "logs", "users", "api-docs", "user-guide"]
)
def test_shared_headers_accessibility_and_card_geometry(name):
    playwright = pytest.importorskip("playwright.sync_api")
    paths = {
        "index": "/",
        "documentation": "/documentation",
        "knowledge": "/knowledge",
        "logs": "/logs",
        "users": "/admin/users",
        "api-docs": "/docs",
        "user-guide": "/static/user-guide.html",
    }
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("**/*", mobile_route)
        page.goto("http://localhost" + paths[name])
        assert page.locator("h1").count() == 1
        assert page.get_by_role("navigation", name="Breadcrumb", exact=True).count() == 1
        assert (
            page.locator(".workspace-breadcrumbs [aria-current=page]").inner_text()
            == page.locator("h1").inner_text()
        )
        assert page.locator(".topbar .page-intro, .topbar .users-intro").is_visible()
        page.screenshot(path=f"/tmp/qls-ui-{name}-desktop.png", full_page=True)
        page.keyboard.press("Tab")
        assert page.locator(".workspace-skip-link").evaluate("e => e === document.activeElement")
        page.keyboard.press("Enter")
        assert page.locator("main").evaluate("e => e === document.activeElement")
        card = page.locator(
            "main .panel:visible, main .knowledge-card:visible, main .section:visible"
        ).first
        if card.count():
            assert card.evaluate("e => getComputedStyle(e).borderRadius") == "14px"
        if name == "users":
            page.locator("#user-role").select_option("release_manager")
            assert "production approval" in page.locator("#role-help").inner_text()
        for theme in ["light", "dark"]:
            page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
            for width in [390, 1440]:
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                assert page.locator(".workspace-breadcrumbs").is_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=f"/tmp/qls-ui-{name}-mobile-dark.png", full_page=True)
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_workspace_header_updates_and_multiselect_is_usable():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("**/*", mobile_route)
        page.goto("http://localhost/")
        page.evaluate("window.navigateWorkspace('/?view=stories', false)")
        assert page.locator(".workspace-breadcrumbs [aria-current=page]").inner_text() == "Stories"
        assert "acceptance criteria" in page.locator(".topbar .page-intro").inner_text()
        page.evaluate("window.navigateWorkspace('/sdlc', false)")
        # Verify the real record selector without inventing project state or credentials.
        height = page.locator("#lifecycle-item-form select[multiple]").evaluate(
            "e => getComputedStyle(e).minHeight"
        )
        assert height == "132px"
        assert page.locator("#lifecycle-timeline-panel").get_attribute("open") is None
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_sdlc_steps_support_keyboard_preview_and_url_restore():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("**/*", mobile_route)
        page.goto("http://localhost/sdlc")
        page.locator("#sdlc-phase-requirements").wait_for()
        assert page.locator('#sdlc-phase-tabs [role="tab"]').count() == 8
        page.locator("#sdlc-phase-requirements").focus()
        page.keyboard.press("End")
        assert page.locator("#sdlc-phase-closure").evaluate("e => e === document.activeElement")
        page.keyboard.press("Enter")
        assert page.locator("#sdlc-step-heading").inner_text() == "Closure"
        assert "phase=closure" in page.url
        assert page.locator("#project-lifecycle").is_hidden()
        page.reload()
        page.locator("#sdlc-phase-closure").wait_for()
        assert page.locator("#sdlc-phase-closure").get_attribute("aria-selected") == "true"
        page.locator("#sdlc-phase-closure").focus()
        page.keyboard.press("Home")
        page.keyboard.press("Enter")
        assert page.locator("#sdlc-step-heading").inner_text() == "Requirements"
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_home_is_sdlc_with_shared_requirements_editor_and_contextual_tools():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", mobile_route)
        page.goto("http://localhost/")
        page.locator("#sdlc-phase-requirements").wait_for()
        assert page.url.endswith("/sdlc")
        assert page.locator("h1").inner_text() == "Project workspace"
        assert page.locator(".sdlc-workspace > .sdlc-project-controls").is_visible()
        assert page.locator("#sdlc-requirements-editor #description").is_visible()
        assert page.locator(".nav-specialist-tools").get_attribute("open") is None
        assert page.locator("#description").count() == 1
        page.locator("#description").fill("A saved draft must survive changing the workflow view.")
        page.locator("#sdlc-phase-backlog").click()
        assert page.locator("#description").is_hidden()
        assert page.locator("#sdlc-project").is_visible()
        page.locator("#sdlc-phase-requirements").click()
        assert page.locator("#description").input_value().startswith("A saved draft")
        page.evaluate("window.navigateWorkspace('/?view=requirements', false)")
        assert page.locator("#test-studio #description").is_visible()
        page.evaluate("window.navigateWorkspace('/sdlc?phase=requirements', false)")
        assert page.locator("#sdlc-requirements-editor #description").is_visible()
        assert page.locator("#description").input_value().startswith("A saved draft")
        assert page.locator(".nav-specialist-tools").get_attribute("open") is not None
        assert page.locator('.nav-specialist-tools a[href="/?view=test-cases"]').is_visible()
        for width in [390, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert not errors
        browser.close()
