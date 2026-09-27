"""Guest UI must not request or link to protected workspace content."""

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from test_mobile_navigation_browser import mobile_route


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("width", [390, 1440])
def test_guest_preview_hides_evidence_and_does_not_fetch_customer_data(width):
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 900})
        api_paths = []
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route(request):
            path = urlparse(request.request.url).path
            if path.startswith("/api/"):
                api_paths.append(path)
            if path == "/":
                html = (Path(__file__).parents[1] / "app/static/index.html").read_text()
                request.fulfill(
                    body=html.replace("<body>", '<body data-guest="true">'),
                    content_type="text/html",
                )
            elif path == "/api/auth/profile":
                request.fulfill(json={"is_guest": True, "display_name": "Guest", "initials": "G"})
            else:
                mobile_route(request)

        page.route("**/*", route)
        page.goto("http://localhost/")
        pw.expect(page.locator(".guest-banner")).to_contain_text("preview")
        pw.expect(page.locator('.primary-nav a[href="/progress"]')).to_be_hidden()
        pw.expect(page.locator('[data-workspace-page="/progress"]')).to_be_hidden()
        pw.expect(page.locator("#generate")).to_be_disabled()
        assert not page.locator('a[href^="/api/automation/reports/"]:visible').count()
        page.wait_for_timeout(300)
        assert set(api_paths) <= {"/api/health", "/api/auth/profile", "/api/automation/languages"}
        assert not errors
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()
