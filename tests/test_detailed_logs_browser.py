"""Opt-in browser checks for the existing runtime log viewer."""

import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_detailed_log_viewer_timestamps_filters_refresh_and_download():
    pw = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    entries = [
        {
            "timestamp": "2026-10-09T17:00:00.123+00:00",
            "level": "INFO",
            "logger": "app.unit",
            "message": "request_complete",
            "request_id": "trace-1",
            "exception": "",
            "details": {"duration_ms": "12.34", "method": "GET", "path": "/api/stlc"},
        },
        {
            "timestamp": "2026-10-09T17:00:01.456+00:00",
            "level": "ERROR",
            "logger": "app.unit",
            "message": "<img src=x onerror=alert(1)>",
            "request_id": "trace-1",
            "exception": "ValueError\napp/service.py:12 in run",
            "details": {"operation": "generation"},
        },
    ]
    calls = []
    errors = []

    def route(request):
        url = urlparse(request.request.url)
        if url.path == "/logs" or url.path.startswith("/static/"):
            file = static / (
                "logs.html" if url.path == "/logs" else url.path.removeprefix("/static/")
            )
            request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif url.path == "/api/logs":
            calls.append(url.query)
            request.fulfill(json={"entries": entries, "count": len(entries)})
        else:
            request.fulfill(json={"display_name": "Reviewer", "is_admin": False})

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.clock.install()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://logs.test/logs?request_id=trace-1")
        pw.expect(page.locator(".log-row")).to_have_count(1)
        assert "request_id=trace-1" in calls[0]
        assert page.locator(".logs-search input[type=search]").count() == 1
        pw.expect(page.locator("#log-reference")).to_have_value("trace-1")
        pw.expect(page.locator("time").first).to_contain_text(".456 UTC")
        assert page.locator(".log-row[open]").count() == 0
        pw.expect(page.locator(".log-record-summary")).to_contain_text("Knowledge graph data")
        pw.expect(page.locator(".log-record-summary")).to_contain_text("2 events")
        pw.expect(page.locator(".record-timeline")).to_be_hidden()
        page.locator(".log-record-summary").click()
        pw.expect(page.locator(".record-timeline")).to_be_visible()
        pw.expect(page.locator(".record-event")).to_have_count(2)
        pw.expect(page.locator(".record-event").first).to_contain_text("request_complete")
        assert page.locator("#log-results img").count() == 0
        page.locator("#log-view-menu > summary").click()
        page.check("#log-detailed")
        assert page.locator(".log-row[open]").count() == 1
        page.uncheck("#log-detailed")
        assert page.locator(".log-row[open]").count() == 0
        page.keyboard.press("Escape")
        pw.expect(page.locator("#log-view-menu")).not_to_have_attribute("open", "")
        page.fill("#log-reference", "generation")
        pw.expect(page.locator(".log-row")).to_have_count(1)
        with page.expect_download() as downloaded:
            page.click("#log-download")
        content = Path(downloaded.value.path()).read_text()
        assert '"operation":"generation"' in content
        assert "request_complete" in content  # Matching records preserve their full context.
        page.fill("#log-reference", "")
        page.locator("#log-view-menu > summary").click()
        page.select_option("#log-timezone", "local")
        page.keyboard.press("Escape")
        pw.expect(page.locator("time").first).to_contain_text(".456")
        page.locator(".log-record-summary").click()
        entries.append(
            {
                **entries[0],
                "message": "new_live_event",
                "timestamp": "2026-10-09T17:00:02.789+00:00",
            }
        )
        page.clock.fast_forward(5000)
        pw.expect(page.locator(".record-event")).to_have_count(3)
        pw.expect(page.locator(".record-timeline")).to_be_visible()
        entries.append({**entries[0], "request_id": "trace-2"})
        page.click("#log-refresh")
        pw.expect(page.locator(".log-row")).to_have_count(2)
        page.fill("#log-reference", "trace-2")
        page.keyboard.press("Enter")
        pw.expect(page.locator("#result-title")).to_have_text("Search results")
        assert "request_id=trace-2" in calls[-1]
        page.fill("#log-reference", "")
        pw.expect(page.locator("#result-title")).to_have_text("Recent logs")
        page.locator("#log-view-menu > summary").click()
        page.uncheck("#log-live")
        page.keyboard.press("Escape")
        count = len(calls)
        page.clock.fast_forward(5000)
        assert len(calls) == count
        page.click("#log-refresh")
        pw.expect(page.locator("#log-updated")).to_contain_text("4 entries loaded")
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#log-view-menu > summary").click()
        box = page.locator(".log-view-options").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_pagination_groups_events_filters_refreshes_and_exports_all_pages():
    import json

    pw = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    entries = [
        {
            "timestamp": f"2026-10-09T17:00:{index:02d}.000+00:00",
            "level": "ERROR" if index % 2 else "INFO",
            "logger": "app.unit",
            "message": "completed",
            "request_id": f"record-{index:02d}",
            "details": {},
        }
        for index in range(45)
    ]
    entries.append({**entries[-1], "message": "related event"})
    errors = []

    def route(request):
        path = urlparse(request.request.url).path
        if path == "/logs" or path.startswith("/static/"):
            file = static / ("logs.html" if path == "/logs" else path.removeprefix("/static/"))
            request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/logs":
            request.fulfill(json={"entries": entries, "count": len(entries)})
        else:
            request.fulfill(json={"display_name": "Reviewer", "is_admin": False})

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.clock.install()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://logs.test/logs")
        pw.expect(page.locator(".log-row")).to_have_count(20)
        pw.expect(page.locator("#log-page-status")).to_have_text("Page 1 of 3")
        pw.expect(page.locator("#log-page-range")).to_have_text("1–20 of 45 loaded records")
        pw.expect(page.locator("#log-page-previous")).to_be_disabled()
        page.locator(".log-row").first.locator("summary").first.click()
        pw.expect(page.locator(".log-row").first.locator(".record-event")).to_have_count(2)
        page.click("#log-page-next")
        pw.expect(page.locator("#log-page-status")).to_have_text("Page 2 of 3")
        page.clock.fast_forward(5000)
        pw.expect(page.locator("#log-page-status")).to_have_text("Page 2 of 3")
        page.click("#log-page-previous")
        pw.expect(page.locator(".log-row").first).to_have_attribute("open", "")
        page.click("#log-page-next")
        page.click("#log-page-next")
        pw.expect(page.locator(".log-row")).to_have_count(5)
        pw.expect(page.locator("#log-page-next")).to_be_disabled()
        with page.expect_download() as download:
            page.click("#log-download")
        exported = Path(download.value.path()).read_text().splitlines()
        assert len(exported) == 46
        assert len({json.loads(line)["request_id"] for line in exported}) == 45
        page.fill("#log-reference", "record-44")
        pw.expect(page.locator("#log-page-status")).to_have_text("Page 1 of 1")
        pw.expect(page.locator(".log-row")).to_have_count(1)
        page.fill("#log-reference", "no matching record")
        pw.expect(page.locator("#log-page-range")).to_have_text("0 loaded records")
        pw.expect(page.locator("#log-page-next")).to_be_disabled()
        page.fill("#log-reference", "")
        page.select_option("#log-page-size", "10")
        pw.expect(page.locator(".log-row")).to_have_count(10)
        pw.expect(page.locator("#log-page-status")).to_have_text("Page 1 of 5")
        page.click("#log-page-next")
        entries[:] = entries[:3]
        page.click("#log-refresh")
        pw.expect(page.locator("#log-page-status")).to_have_text("Page 1 of 1")
        pw.expect(page.locator(".log-row")).to_have_count(3)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_operation_link_shows_readable_agent_activity_without_technical_logs():
    pw = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    state = {
        "events": [
            {
                "sequence": 1,
                "agent": "BA Agent",
                "action": "ba_review_knowledge",
                "status": "success",
                "summary": "Prepared domain knowledge <img src=x>.",
            },
            {
                "sequence": 2,
                "agent": "AI Provider",
                "action": "provider_wait",
                "status": "running",
                "summary": "Codex is generating the review (20s elapsed).",
            },
            {
                "sequence": 3,
                "agent": "AI Provider",
                "action": "provider_wait",
                "status": "running",
                "summary": "Codex is generating the review (30s elapsed).",
            },
            {
                "sequence": 4,
                "agent": "AI Provider",
                "action": "provider_response",
                "status": "success",
                "summary": "Review response received.",
            },
            {
                "sequence": 5,
                "agent": "Artifact Validator",
                "action": "validate_artifact",
                "status": "success",
                "summary": "Review citations checked.",
            },
        ],
        "complete": True,
    }
    calls, errors = [], []

    def route(request):
        url = urlparse(request.request.url)
        if url.path == "/logs" or url.path.startswith("/static/"):
            file = static / (
                "logs.html" if url.path == "/logs" else url.path.removeprefix("/static/")
            )
            request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif url.path == "/api/logs":
            request.fulfill(json={"entries": [], "count": 0})
        elif url.path == "/api/generation/trace-activity/events":
            calls.append(url.path)
            request.fulfill(
                json=state
                | {
                    "events": [
                        event | {"timestamp": "2026-10-13T10:00:00Z"} for event in state["events"]
                    ]
                }
            )
        else:
            request.fulfill(json={"display_name": "Reviewer", "is_admin": False})

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://logs.test/logs?request_id=trace-activity&view=activity")
        pw.expect(page.locator("h1")).to_have_text("Operation activity")
        pw.expect(page.locator("#request-activity-status")).to_contain_text("finished")
        pw.expect(page.locator("#request-activity-events li")).to_have_count(4)
        pw.expect(page.locator("#request-activity-events")).to_contain_text("30s elapsed")
        pw.expect(page.locator("#request-activity-events")).not_to_contain_text("20s elapsed")
        pw.expect(page.locator("#request-activity-events")).to_contain_text(
            "Review citations checked"
        )
        assert page.locator("#request-activity-events img").count() == 0
        state.update(events=[], complete=False)
        page.locator("#log-refresh").click()
        pw.expect(page.locator("#request-activity-status")).to_contain_text("server restart")
        assert len(calls) >= 2
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        browser.close()
