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

    def requirement(identifier, project, key, version, status, owner):
        return {
            "id": identifier,
            "project": project,
            "key": key,
            "version": version,
            "status": status,
            "owner": owner,
            "title": "Quotation <scope>",
            "description": "Approved quotation requirements",
            "source": "BRD-01",
            "acceptance_criteria": ["Retain approved values"],
            "created_at": now,
            "quality_flags": [],
        }

    data = {
        "requirements": [
            requirement("r1", "PCP", "REQ-1", 1, "draft", "Old owner"),
            requirement("r2", "PCP", "REQ-1", 2, "approved", "Alex"),
            requirement("r3", "HP", "REQ-2", 1, "draft", "Sam"),
        ],
        "baselines": [
            {
                "id": "b1",
                "project": "PCP",
                "name": "Release scope",
                "status": "approved",
                "requirements": [{"id": "r2"}],
                "created_at": now,
            }
        ],
        "suites": [{"id": "s1", "project": "PCP", "created_at": now}],
        "cycles": [
            {
                "id": "c1",
                "project": "PCP",
                "name": "Release verification",
                "build": "1.2",
                "environment": "UAT",
                "assignments": {"TC-1": "Alex"},
                "created_at": now,
            }
        ],
        "defects": [
            {"id": "d1", "cycle_id": "c1", "status": "open", "created_at": now},
            {"id": "other", "cycle_id": "other", "status": "open"},
        ],
        "audit": [],
        "attempts": [],
        "impacts": [{"suite_id": "s1"}],
    }
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
            elif path == "/api/stlc":
                request.fulfill(
                    status=503 if fail else 200,
                    json=data,
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
        page.locator("#pm-project").select_option("PCP")
        pw.expect(page.locator("#pm-project-title")).to_have_text("PCP")
        pw.expect(page.locator("#pm-metrics strong")).to_have_text(["1", "1", "1", "1"])
        pw.expect(page.locator("#pm-project-details")).to_contain_text("Alex")
        pw.expect(page.locator("#pm-project-details")).not_to_contain_text("Old owner")
        pw.expect(page.locator("#pm-requirements")).to_contain_text("Quotation <scope>")
        pw.expect(page.locator("#pm-requirements")).to_contain_text("Version 2")
        pw.expect(page.locator("#pm-cycles")).to_contain_text("UAT")
        pw.expect(page.locator("#pm-attention")).to_contain_text("1 requirement changes")
        page.locator("#pm-search").fill("missing")
        pw.expect(page.locator("#pm-requirements")).to_contain_text("No requirements match")
        page.locator("#pm-project").select_option("HP")
        pw.expect(page.locator("#pm-metrics strong")).to_have_text(["1", "0", "0", "0"])
        pw.expect(page.locator("#pm-project-details")).to_contain_text("Sam")
        pw.expect(page.locator("#pm-cycles")).not_to_contain_text("UAT")
        pw.expect(page.locator("#pm-attention")).to_contain_text("need review")
        page.locator("#pm-project").select_option("PCP")
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
        for key in data:
            data[key] = []
        page.locator("#pm-refresh").click()
        pw.expect(page.locator("#pm-project-title")).to_have_text("Your project at a glance")
        pw.expect(page.locator("#pm-requirements")).to_contain_text("No requirements saved")
        browser.close()
