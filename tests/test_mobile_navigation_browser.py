"""Touch navigation, drawer geometry, keyboard escape and responsive page smoke checks."""

import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

PAGES = {
    "/": "index.html",
    "/documentation": "documentation.html",
    "/static/user-guide.html": "user-guide.html",
    "/knowledge": "knowledge.html",
    "/logs": "logs.html",
    "/users": "users.html",
    "/docs": "api-docs.html",
    "/project-dashboard": "index.html",
    "/progress": "index.html",
    "/quality-lifecycle": "index.html",
}


def mobile_route(route):
    root = Path(__file__).parents[1] / "app/static"
    path = urlparse(route.request.url).path
    if path in PAGES or path.startswith("/static/"):
        file = root / PAGES.get(path, path.removeprefix("/static/"))
        route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        return
    data = {
        "models": [],
        "events": [],
        "history": [],
        "active": [],
        "business_rules": [],
        "usage": {},
        "complete": True,
    }
    if path == "/api/auth/profile":
        data = {"display_name": "Reviewer", "initials": "RE", "is_admin": True}
    elif path in {"/api/agents", "/api/admin/users"}:
        data = []
    elif path == "/api/logs":
        data = {"count": 0, "entries": []}
    elif path == "/api/workspace/knowledge":
        data = {
            "suite_count": 0,
            "approved_output_count": 0,
            "scenario_count": 0,
            "enabled": True,
            "suites": [],
            "approved_outputs": [],
            "workflow_counts": {"stories": 0, "scenarios": 0},
        }
    elif path.startswith("/api/documentation/company"):
        data = {"content": "# Guide"}
    elif path == "/openapi.json":
        data = {
            "openapi": "3.1.0",
            "info": {"title": "API", "version": "1"},
            "paths": {},
            "components": {
                "schemas": {
                    "Body_import_business_rule_document_api_business_rules_document_post": {
                        "type": "object",
                        "properties": {"file": {"type": "string"}},
                    }
                }
            },
        }
    route.fulfill(json=data)


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("path", PAGES)
@pytest.mark.parametrize(
    "engine,width,height",
    [
        ("chromium", 320, 568),
        ("chromium", 390, 844),
        ("chromium", 768, 1024),
        ("webkit", 390, 844),
    ],
)
def test_mobile_navigation_and_page_layout(path, engine, width, height):
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as runtime:
        browser = getattr(runtime, engine).launch()
        context = browser.new_context(viewport={"width": width, "height": height}, has_touch=True)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", mobile_route)
        page.goto("http://localhost" + path)
        toggle = page.locator("#sidebar-toggle")
        pw.expect(toggle).to_have_attribute("aria-expanded", "false")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), path
        assert toggle.bounding_box()["height"] >= 44
        toggle.tap()
        pw.expect(toggle).to_have_attribute("aria-expanded", "true")
        drawer = page.locator("#sidebar-content")
        bounds = drawer.bounding_box()
        assert bounds["height"] > height / 2, f"Drawer clipped: {bounds}"
        assert bounds["y"] >= page.locator(".sidebar-header").bounding_box()["height"]
        assert bounds["y"] + bounds["height"] <= height + 1
        assert page.locator("main").evaluate("e => e.inert")
        page.locator("#theme-gear").tap()
        page.locator('[data-theme-option="dark"]').tap()
        pw.expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#theme-gear").tap()
        page.keyboard.press("Escape")
        pw.expect(page.locator("#theme-menu")).to_be_hidden()
        pw.expect(toggle).to_have_attribute("aria-expanded", "true")
        page.keyboard.press("Escape")
        pw.expect(toggle).to_have_attribute("aria-expanded", "false")
        pw.expect(toggle).to_be_focused()
        assert not page.locator("main").evaluate("e => e.inert")
        toggle.tap()
        page.touchscreen.tap(width - 12, 160)
        pw.expect(toggle).to_have_attribute("aria-expanded", "false")
        toggle.tap()
        page.locator('.primary-nav a[href="/knowledge"]').tap()
        pw.expect(page).to_have_url("http://localhost/knowledge")
        pw.expect(toggle).to_have_attribute("aria-expanded", "false")
        assert not page.locator("main").evaluate("e => e.inert")
        toggle.tap()
        page.set_viewport_size({"width": 1440, "height": 900})
        pw.expect(page.locator(".navigation-backdrop")).to_be_hidden()
        assert not page.locator("main").evaluate("e => e.inert")
        assert not errors, errors
        context.close()
        browser.close()


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
@pytest.mark.parametrize("width,height", [(390, 844), (844, 390)])
def test_mobile_scroll_focus_popovers_and_landscape(engine, width, height):
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as runtime:
        browser = getattr(runtime, engine).launch()
        page = browser.new_page(viewport={"width": width, "height": height}, has_touch=True)
        page.route("**/*", mobile_route)
        page.goto("http://localhost/")
        page.evaluate("window.scrollTo({top: 600, behavior: 'instant'})")
        original_scroll = page.evaluate("scrollY")
        toggle = page.locator("#sidebar-toggle")
        assert toggle.bounding_box()["y"] >= 0, "Menu must remain reachable after scrolling"
        toggle.tap()
        drawer = page.locator("#sidebar-content")
        assert drawer.bounding_box()["height"] > height / 2
        assert drawer.bounding_box()["y"] + drawer.bounding_box()["height"] <= height + 1
        page.locator(".sidebar .brand").focus()
        page.keyboard.press("Shift+Tab")
        pw.expect(page.locator("#theme-gear")).to_be_focused()
        page.keyboard.press("Tab")
        pw.expect(page.locator(".sidebar .brand")).to_be_focused()
        page.locator("#theme-gear").tap()
        page.locator('[data-theme-option="dark"]').tap()
        pw.expect(page.locator(".primary-nav a:not(.active)").first).to_have_css(
            "color", "rgb(216, 219, 232)"
        )
        assert toggle.bounding_box()["y"] >= 0, "Theme selection must not scroll header away"
        page.screenshot(path=f"/tmp/mobile-drawer-{engine}-{width}.png")
        toggle.tap()
        assert abs(page.evaluate("scrollY") - original_scroll) <= 1
        assert not page.locator("main").evaluate("e => e.inert")
        page.set_viewport_size({"width": 390, "height": 844})
        page.evaluate("window.scrollTo(0, 0)")
        for trigger, panel in [
            ("profile-toggle", "profile-panel"),
            ("notification-bell", "notification-panel"),
        ]:
            page.locator(f"#{trigger}").tap()
            pw.expect(page.locator(f"#{panel}")).to_be_visible()
            bounds = page.locator(f"#{panel}").bounding_box()
            assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
            assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 844
            page.keyboard.press("Escape")
            pw.expect(page.locator(f"#{panel}")).to_be_hidden()
        page.goto("http://localhost/static/login.html")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#password").fill("synthetic-test-password")
        page.locator("#password-toggle").tap()
        pw.expect(page.locator("#password")).to_have_attribute("type", "text")
        page.locator("#password-toggle").tap()
        pw.expect(page.locator("#password")).to_have_attribute("type", "password")
        page.locator("#login-button").scroll_into_view_if_needed()
        assert page.locator("#login-button").bounding_box()["height"] >= 44
        browser.close()
