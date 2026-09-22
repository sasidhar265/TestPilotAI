"""Verify management reporting against known history without live provider calls."""

import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_project_dashboard_evidence_filters_and_refresh():
    pw = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    now = datetime.now(UTC).isoformat()
    cases = [
        {"id": "TC-1", "execution": "passed"},
        {"id": "TC-2", "execution": "failed"},
        {"id": "TC-3", "execution": "not-run"},
    ]
    details = {"suite_key": "abc123", "feature": "PCP quotation", "validated": True, "cases": cases}
    history = [
        {"operation": "case_execution", "finished_at": now, "details": details},
        {"operation": "test_generation", "finished_at": now, "details": details},
        {"operation": "test_generation", "finished_at": now, "details": details},
        {"operation": "repository_checks", "finished_at": now, "details": {"passed": 100}},
        {
            "operation": "test_generation",
            "finished_at": "2020-01-01T00:00:00Z",
            "details": {
                "suite_key": "old456",
                "feature": "HP quotation",
                "validated": False,
                "cases": [],
            },
        },
    ]
    fail = False
    with pw.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        def route(request):
            path = urlparse(request.request.url).path
            if path == "/project-dashboard" or path.startswith("/static/"):
                file = static / (
                    "index.html" if path == "/project-dashboard" else path.removeprefix("/static/")
                )
                request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
            elif path == "/api/dashboard":
                request.fulfill(
                    status=503 if fail else 200,
                    json={"history": history, "active": [], "scope": "Retained history"},
                )
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
        page.goto("http://localhost/project-dashboard")
        pw.expect(page.locator("#pm-content")).to_be_visible()
        pw.expect(page.locator("#pm-suite-count")).to_have_text("1 versions")
        pw.expect(page.locator("#pm-metrics strong")).to_have_text(["1", "1", "1", "0"])
        pw.expect(page.locator("#pm-outcomes")).to_contain_text("failed")
        pw.expect(page.locator("#pm-suites")).to_contain_text("1 passed / 3 recorded")
        pw.expect(page.locator('[data-outcome="not_run"] strong')).to_have_text("1")
        page.locator("#pm-period").select_option("0")
        pw.expect(page.locator("#pm-suite-count")).to_have_text("2 versions")
        page.locator("#pm-search").fill("HP")
        pw.expect(page.locator("#pm-suite-count")).to_have_text("1 versions")
        pw.expect(page.locator("#pm-attention")).to_contain_text("no recorded case execution")
        page.locator("#pm-search").fill("missing")
        pw.expect(page.locator("#pm-suites")).to_contain_text("No suite versions")
        page.locator("#pm-search").fill("")
        page.screenshot(path="/tmp/project-dashboard-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path="/tmp/project-dashboard-mobile.png", full_page=True)
        fail = True
        page.locator("#pm-refresh").click()
        pw.expect(page.locator("#pm-status")).to_contain_text("could not be loaded")
        pw.expect(page.locator("#pm-content")).to_be_hidden()
        fail = False
        page.locator("#pm-refresh").click()
        pw.expect(page.locator("#pm-content")).to_be_visible()
        browser.close()
