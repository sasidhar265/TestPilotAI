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
                 summary: 'Current request <reference>'},
                {sequence: 5, agent: 'Story Agent',
                 action: 'validation_basis', status: 'passed',
                 summary: 'Password reset: checked 2 stories against exact source excerpts.'},
                {sequence: 6, agent: 'Story Agent',
                 action: 'validation_source', status: 'info',
                 summary: 'Request abc123; ST-001: Expired link'},
                {sequence: 7, agent: 'Scenario Agent',
                 action: 'validation_basis', status: 'passed',
                 summary: 'Password reset: checked 3 scenarios and story ownership.'},
                {sequence: 8, agent: 'Scenario Agent',
                 action: 'validation_source', status: 'info',
                 summary: 'Reviewed stories abc456; SC-001 → ST-001'},
                {sequence: 9, agent: 'Quality Gate · manual',
                 action: 'validation_basis', status: 'passed',
                 summary: 'Checked 2 manual password reset cases.'},
                {sequence: 10, agent: 'Quality Gate · automation',
                 action: 'validation_basis', status: 'failed',
                 summary: 'Checked 3 automation password reset cases; TC-003 failed.'}
            ]);
        }""")
        panel = page.locator("#generation-validation-evidence")
        pw.expect(panel).to_contain_text("Zero blocking errors; one warning")
        pw.expect(panel).to_contain_text("Current request <reference>")
        pw.expect(panel).not_to_contain_text("Earlier reference")
        pw.expect(panel.locator("reference")).to_have_count(0)
        pw.expect(panel).to_contain_text("2 stories against exact source excerpts")
        pw.expect(panel).to_contain_text("SC-001 → ST-001")
        pw.expect(panel).to_contain_text("2 manual password reset cases")
        pw.expect(panel).to_contain_text("3 automation password reset cases")
        pw.expect(panel.locator("article")).to_have_count(5)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path="/tmp/validation-overlay-mobile.png", full_page=True)
        page.evaluate("resetLifecycleFeed()")
        pw.expect(panel).to_contain_text("No checks have been reported yet")
        pw.expect(panel).not_to_contain_text("Current request")
        browser.close()
