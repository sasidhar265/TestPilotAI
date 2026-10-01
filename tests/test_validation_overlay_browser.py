"""Validation evidence shown by the generation overlay, without provider calls."""

import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_validation_overlay_sources_retries_and_reset():
    pw = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    with pw.sync_playwright() as api:
        browser = api.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})

        def route(request):
            path = urlparse(request.request.url).path
            if path == "/" or path.startswith("/static/"):
                file = static / ("index.html" if path == "/" else path.removeprefix("/static/"))
                request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
            else:
                request.fulfill(
                    json={
                        "models": [],
                        "history": [],
                        "active": [],
                        "events": [],
                        "business_rules": [],
                    }
                )

        page.route("**/*", route)
        page.goto("http://localhost/")
        page.evaluate("""() => {
            resetLifecycleFeed();
            document.getElementById('generation-overlay').classList.remove('hidden');
            renderLifecycleEvents([
                {sequence: 1, agent: 'Quality Gate',
                 action: 'validation_basis', status: 'failed',
                 summary: 'Two blocking errors.'},
                {sequence: 2, agent: 'Quality Gate',
                 action: 'validation_source', status: 'info',
                 summary: 'Earlier reference'},
                {sequence: 3, agent: 'Quality Gate',
                 action: 'validation_basis', status: 'passed',
                 summary: 'Zero blocking errors; one warning. Not test execution.'},
                {sequence: 4, agent: 'Quality Gate',
                 action: 'validation_source', status: 'info',
                 summary: 'Current request <reference>'}
            ]);
        }""")
        panel = page.locator("#generation-validation-evidence")
        pw.expect(panel).to_contain_text("Zero blocking errors; one warning")
        pw.expect(panel).to_contain_text("Current request <reference>")
        pw.expect(panel).not_to_contain_text("Earlier reference")
        pw.expect(panel.locator("reference")).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path="/tmp/validation-overlay-mobile.png", full_page=True)
        page.evaluate("resetLifecycleFeed()")
        pw.expect(panel).to_contain_text("No checks have been reported yet")
        pw.expect(panel).not_to_contain_text("Current request")
        browser.close()
