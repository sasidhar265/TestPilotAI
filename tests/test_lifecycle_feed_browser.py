"""Slow lifecycle polling must not duplicate or mix operation progress."""

import mimetypes
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_lifecycle_feed_deduplicates_slow_polls_and_ignores_previous_run():
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    pending = {}

    def route(request):
        url = urlparse(request.request.url)
        path = url.path
        if path == "/" or path.startswith("/static/"):
            file = static / ("index.html" if path == "/" else path.removeprefix("/static/"))
            request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path.startswith("/api/generation/") and path.endswith("/events"):
            run = path.split("/")[3]
            if parse_qs(url.query).get("after") == ["0"]:
                pending.setdefault(run, []).append(request)
            else:
                request.fulfill(json={"events": [], "complete": True})
        elif path == "/api/auth/profile":
            request.fulfill(json={"display_name": "Reviewer", "is_admin": False})
        else:
            request.fulfill(json={"models": [], "events": [], "history": [], "active": [], "business_rules": []})

    def event(agent):
        return {"sequence": 1, "agent": agent, "summary": "One step completed", "status": "success"}

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.route("**/*", route)
        page.goto("http://localhost/")
        page.evaluate("startLifecycleFeed('slow-run')")
        page.wait_for_timeout(800)
        assert len(pending["slow-run"]) == 1
        pending["slow-run"].pop().fulfill(json={"events": [event("Input Agent")], "complete": False})
        playwright.expect(page.locator("#live-agent-events li")).to_have_count(1)
        playwright.expect(page.locator("#generation-background-events li")).to_have_count(1)
        page.evaluate("stopLifecycleFeed('slow-run')")

        page.evaluate("startLifecycleFeed('old-run')")
        page.wait_for_timeout(100)
        assert len(pending.get("old-run", [])) == 1
        page.evaluate("startLifecycleFeed('new-run')")
        page.wait_for_timeout(100)
        assert len(pending.get("new-run", [])) == 1
        pending["old-run"].pop().fulfill(json={"events": [event("Old Agent")], "complete": True})
        pending["new-run"].pop().fulfill(json={"events": [event("New Agent")], "complete": True})
        playwright.expect(page.locator("#live-agent-events li")).to_have_count(1)
        playwright.expect(page.locator("#live-agent-events")).to_contain_text("New Agent")
        playwright.expect(page.locator("#live-agent-events")).not_to_contain_text("Old Agent")
        browser.close()


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_generation_submit_starts_only_one_request_while_rules_are_saving():
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    pending_rule_saves = []
    generation_calls = []

    def route(request):
        path = urlparse(request.request.url).path
        if path == "/static/scripts/workflow.js":
            request.fulfill(body="", content_type="application/javascript")
        elif path == "/" or path.startswith("/static/"):
            file = static / ("index.html" if path == "/" else path.removeprefix("/static/"))
            request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/workspace/rules" and request.request.method == "PUT":
            pending_rule_saves.append(request)
        elif path == "/api/workspace/rules":
            request.fulfill(json={"business_rules": []})
        elif path == "/api/agent/run":
            generation_calls.append(request)
            request.fulfill(status=422, json={"detail": "Simulated generation stop"})
        elif path == "/api/auth/profile":
            request.fulfill(json={"display_name": "Reviewer", "is_admin": False})
        else:
            request.fulfill(json={"models": [], "events": [], "history": [], "active": [], "business_rules": []})

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.route("**/*", route)
        page.goto("http://localhost/")
        page.locator("#description").fill("Quotation requests must reject a negative deposit.")
        page.evaluate("""() => {
          const form = document.getElementById('generate-form');
          form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
          form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        }""")
        page.wait_for_timeout(150)
        assert len(pending_rule_saves) == 1
        pending_rule_saves.pop().fulfill(json={"business_rules": []})
        playwright.expect(page.locator("#status")).to_contain_text("Simulated generation stop")
        assert len(generation_calls) == 1
        browser.close()
