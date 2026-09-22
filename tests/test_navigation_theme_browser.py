import mimetypes
import os
from pathlib import Path

import pytest


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("name", ["index", "documentation", "knowledge", "logs", "users"])
def test_collapsed_sidebar_theme_options_escape_sidebar_and_persist(name):
    root = Path(__file__).parents[1] / "app/static"
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        def route(r):
            path = r.request.url.split("localhost")[-1].split("?")[0]
            if path == "/" or path.startswith("/static/"):
                f = root / (name + ".html" if path == "/" else path.removeprefix("/static/"))
                r.fulfill(body=f.read_bytes(), content_type=mimetypes.guess_type(f)[0])
                return
            data = {}
            if path == "/api/auth/profile":
                data = {
                    "display_name": "Admin",
                    "initials": "AD",
                    "username": "admin",
                    "is_admin": True,
                }
            elif path in ["/api/agents", "/api/admin/users"]:
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
                }
            elif path.startswith("/api/documentation/company"):
                data = {"content": "# Guide"}
            elif path == "/api/llm/models":
                data = {"models": []}
            r.fulfill(json=data)

        page.route("**/*", route)
        page.goto("http://localhost/")
        page.locator("#sidebar-toggle").click()
        for theme in ["dark", "light", "system"]:
            page.locator("#theme-gear").click()
            button = page.locator(f'[data-theme-option="{theme}"]')
            box = button.bounding_box()
            hit = button.evaluate(
                "(e)=>{const r=e.getBoundingClientRect();"
                "return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}"
            )
            assert page.locator("#theme-menu").evaluate("(e)=>e.parentElement===document.body")
            assert box["x"] >= page.locator(".sidebar").bounding_box()["width"]
            assert page.locator(".sidebar").evaluate("(e)=>e.scrollLeft") == 0
            assert hit, f"{name}: theme option clipped or covered"
            button.click(timeout=3000)
            assert page.evaluate("localStorage.getItem('quality-lifecycle-studio-theme')") == theme
            assert page.locator("#theme-menu").is_hidden()
        page.reload()
        assert page.locator("#sidebar-toggle").get_attribute("aria-expanded") == "false"
        if name in {"documentation", "knowledge", "logs"}:
            page.screenshot(path=f"/tmp/explore-{name}-desktop.png", full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=f"/tmp/explore-{name}-mobile.png", full_page=True)
        page.close()
        browser.close()
