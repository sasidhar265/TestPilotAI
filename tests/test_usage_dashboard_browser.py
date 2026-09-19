"""Opt-in UI checks using fixture data; no billable provider requests."""

import mimetypes
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_usage_dashboard_filters_themes_empty_error_and_navigation():
    playwright = pytest.importorskip("playwright.sync_api")
    root = Path(__file__).parents[1] / "app/static"
    periods = []
    failure = False
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        def route(r):
            nonlocal failure
            url = urlparse(r.request.url)
            path = url.path
            if path in ["/", "/quality-lifecycle"] or path.startswith("/static/"):
                f = root / (
                    "index.html"
                    if path in ["/", "/quality-lifecycle"]
                    else path.removeprefix("/static/")
                )
                r.fulfill(body=f.read_bytes(), content_type=mimetypes.guess_type(f)[0])
                return
            if path == "/api/dashboard":
                days = parse_qs(url.query).get("days", ["30"])[0]
                periods.append(days)
                if failure:
                    r.fulfill(status=503, json={"detail": "Unavailable"})
                    return
                empty = days == "7"
                r.fulfill(
                    json={
                        "usage": {
                            "totals": {
                                "manual": 0 if empty else 240,
                                "automation": 0 if empty else 180,
                                "runs": 0 if empty else 18,
                                "reused": 32,
                                "failed": 1,
                                "validation_failed": 2,
                            },
                            "models": []
                            if empty
                            else [
                                {
                                    "provider": "openai-api",
                                    "model": "gpt-5.4",
                                    "calls": 12,
                                    "input_tokens": 125000,
                                    "cached_tokens": 25000,
                                    "output_tokens": 15000,
                                    "cost_usd": 0.48125,
                                    "unpriced_calls": 0,
                                    "unmetered_calls": 0,
                                },
                                {
                                    "provider": "codex-cli",
                                    "model": "<img src=x onerror=alert(1)>",
                                    "calls": 2,
                                    "input_tokens": None,
                                    "cached_tokens": None,
                                    "output_tokens": None,
                                    "cost_usd": None,
                                    "unpriced_calls": 2,
                                    "unmetered_calls": 2,
                                },
                            ],
                            "daily": []
                            if empty
                            else [{"day": "2026-09-19", "manual": 240, "automation": 180}],
                            "scope": "Shared workspace. Historical tokens unavailable.",
                        }
                    }
                )
                return
            data = {}
            if path == "/api/auth/profile":
                data = {"display_name": "Reviewer", "initials": "RE", "is_admin": True}
            elif path in ["/api/agents", "/api/admin/users"]:
                data = []
            r.fulfill(json=data)

        page.route("**/*", route)
        page.goto("http://localhost/")
        assert not periods
        page.locator('.primary-nav a[href="/quality-lifecycle"]').click()
        playwright.expect(page.locator("#usage-cards")).to_contain_text("240")
        playwright.expect(page.locator("#usage-cards")).to_contain_text("$0.4813")
        playwright.expect(page.locator("#usage-cards")).to_contain_text("Partial subtotal")
        assert page.locator("#usage-models img").count() == 0
        page.screenshot(path="/tmp/usage-dashboard-desktop.png", full_page=True)
        page.evaluate("document.documentElement.dataset.theme='dark'")
        page.screenshot(path="/tmp/usage-dashboard-dark.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path="/tmp/usage-dashboard-mobile.png", full_page=True)
        page.locator("#usage-period").select_option("7")
        playwright.expect(page.locator("#usage-trend")).to_contain_text(
            "No test generation recorded"
        )
        playwright.expect(page.locator("#usage-models")).to_contain_text("No model usage recorded")
        playwright.expect(page.locator("#usage-cards")).to_contain_text("Unavailable")
        failure = True
        page.locator("#refresh-usage").click()
        playwright.expect(page.locator("#usage-status")).to_contain_text("Use Refresh to try again")
        playwright.expect(page.locator("#usage-content")).to_be_hidden()
        failure = False
        page.locator("#usage-period").select_option("0")
        playwright.expect(page.locator("#usage-content")).to_be_visible()
        assert periods[-1] == "0"
        page.reload()
        playwright.expect(page.locator("#usage-content")).to_be_visible()
        browser.close()
