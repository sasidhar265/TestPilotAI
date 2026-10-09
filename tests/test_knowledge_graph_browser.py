"""Interactive graph verification using existing read-only lifecycle endpoints."""

import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("empty", [True, False])
def test_graph_sources_selection_search_zoom_and_mobile_layout(empty):
    pw = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    snapshot = {
        "requirements": [
            {
                "id": "req",
                "project": "Alpha",
                "key": "REQ-1",
                "version": 1,
                "title": "<img src=x onerror=alert(1)>",
                "status": "approved",
            }
        ],
        "baselines": [
            {
                "id": "base",
                "project": "Alpha",
                "name": "Reviewed baseline",
                "status": "approved",
                "requirements": [{"id": "req", "key": "REQ-1"}],
            }
        ],
        "suites": [
            {
                "id": "suite",
                "project": "Alpha",
                "baseline_id": "base",
                "status": "approved",
                "mappings": {"TC-1": ["REQ-1"]},
                "suite": {
                    "feature_name": "Service checks",
                    "test_cases": [{"id": "TC-1", "title": "Service check"}],
                },
            }
        ],
    }
    errors = []

    def route(request):
        path = urlparse(request.request.url).path
        if path == "/knowledge" or path.startswith("/static/"):
            file = static / (
                "knowledge.html" if path == "/knowledge" else path.removeprefix("/static/")
            )
            request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/stlc":
            request.fulfill(json={} if empty else snapshot)
        elif path == "/api/workspace/knowledge":
            request.fulfill(
                json={
                    "enabled": False,
                    "suite_count": 0,
                    "approved_output_count": 0,
                    "scenario_count": 0,
                    "suites": [],
                    "approved_outputs": [],
                }
            )
        else:
            request.fulfill(json={"display_name": "Reviewer", "is_admin": False})

    with pw.sync_playwright() as runtime:
        options = (
            {"executable_path": os.environ["PLAYWRIGHT_CHROMIUM_EXECUTABLE"]}
            if os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            else {}
        )
        browser = runtime.chromium.launch(**options)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.clock.install()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://graph.test/knowledge?view=graph")
        pw.expect(page.locator(".graph-node")).to_have_count(8 if empty else 5)
        pw.expect(page.locator("#graph-source")).to_have_value("example" if empty else "live")
        if empty:
            pw.expect(page.locator("#graph-status")).to_contain_text("illustrative records only")
            page.select_option("#graph-source", "live")
            pw.expect(page.locator("#graph-empty")).to_be_visible()
            pw.expect(page.locator("#knowledge-graph")).to_be_hidden()
            page.select_option("#graph-source", "example")
        page.locator(".graph-node[aria-label^='Requirement']").click()
        pw.expect(page.locator("#graph-detail-title")).to_contain_text("REQ")
        if not empty:
            pw.expect(page.locator("#graph-detail-fields")).to_contain_text(
                snapshot["requirements"][0]["title"]
            )
            assert page.locator("#graph-detail-fields img").count() == 0
        assert page.locator("#graph-detail-links button").count() > 0
        page.locator("#graph-detail-links button").first.click()
        page.fill("#graph-search", "no matching records")
        pw.expect(page.locator("#graph-empty")).to_contain_text("No matching nodes")
        page.fill("#graph-search", "")
        page.click("#tree-tab")
        pw.expect(page.locator("#tree-tab")).to_have_attribute("aria-selected", "true")
        pw.expect(page.locator(".graph-node")).to_have_count(8 if empty else 5)
        assert page.locator(".graph-edge").count() == (7 if empty else 4)
        page.locator(".graph-node").last.click()
        pw.expect(page.locator(".graph-node.is-selected")).to_have_count(1)
        page.locator(".graph-markdown summary").click()
        pw.expect(page.locator("#graph-markdown-source")).to_contain_text("flowchart TD")
        with page.expect_download() as download:
            page.click("#graph-download")
        assert download.value.suggested_filename.endswith(".md")
        page.locator("#tree-tab").focus()
        page.keyboard.press("ArrowLeft")
        pw.expect(page.locator("#graph-tab")).to_have_attribute("aria-selected", "true")
        pw.expect(page.locator("#graph-markdown-source")).to_contain_text("flowchart LR")
        node = page.locator(".graph-node").first
        node.hover()
        before_position = node.get_attribute("transform")
        before_paths = page.locator(".edge-line").evaluate_all(
            "els => els.map(e => e.getAttribute('d'))"
        )
        box = node.bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(
            box["x"] + box["width"] / 2 + 40, box["y"] + box["height"] / 2 + 20, steps=5
        )
        page.mouse.up()
        assert node.get_attribute("transform") != before_position
        after_paths = page.locator(".edge-line").evaluate_all(
            "els => els.map(e => e.getAttribute('d'))"
        )
        assert before_paths != after_paths
        node.click()
        assert page.locator(".graph-edge.is-selected").count() > 0
        before_zoom = page.locator("#graph-zoom-level").inner_text()
        page.mouse.wheel(0, -300)
        pw.expect(page.locator("#graph-zoom-level")).not_to_have_text(before_zoom)
        page.click("#graph-reset")
        assert node.get_attribute("transform") == before_position
        page.click("#graph-expand")
        pw.expect(page.locator("#graph-workspace")).to_have_class("graph-workspace is-expanded")
        page.keyboard.press("Escape")
        pw.expect(page.locator("#graph-workspace")).to_have_class("graph-workspace")
        for _ in range(4):
            page.click("#graph-zoom-in")
        canvas = page.locator("#graph-canvas")
        canvas.evaluate("el => el.scrollTo(0, 0)")
        box = canvas.bounding_box()
        page.mouse.move(box["x"] + 20, box["y"] + 20)
        page.mouse.down()
        page.mouse.move(box["x"] - 50, box["y"] - 30, steps=5)
        page.mouse.up()
        assert canvas.evaluate("el => el.scrollLeft") > 0
        page.click("#graph-fit")
        if not empty:
            snapshot["requirements"][0]["title"] = "Updated live requirement"
        page.clock.fast_forward(30000)
        pw.expect(page.locator("#graph-live-state")).to_contain_text("Updated")
        if not empty:
            page.locator(".graph-node[aria-label^='Requirement']").click()
            pw.expect(page.locator("#graph-detail-fields")).to_contain_text(
                "Updated live requirement"
            )
        before = page.locator("#graph-zoom-level").inner_text()
        page.click("#graph-zoom-in")
        assert page.locator("#graph-zoom-level").inner_text() != before
        page.locator(".graph-node").first.focus()
        page.keyboard.press("Enter")
        pw.expect(page.locator(".graph-node.is-selected")).to_have_count(1)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        browser.close()
