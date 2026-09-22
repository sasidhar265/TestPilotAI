"""The workflow exposes failed BRD findings as an editable download."""

import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_failed_uploaded_brd_shows_suggestions_preview_and_download():
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    source = "The quotation permits a negative deposit."
    report = {
        "status": "blocked",
        "message": "Requirements blocked: resolve the business-alignment findings before continuing.",
        "findings": [{
            "requirement_id": "REQ-001",
            "status": "conflict",
            "reason": "Negative deposits conflict with the approved rule.",
            "suggested_change": "Reject a negative deposit.",
            "evidence": [],
        }],
        "requirements": {"REQ-001": source},
    }

    def route(request):
        path = urlparse(request.request.url).path
        if path == "/" or path.startswith("/static/"):
            file = static / ("index.html" if path == "/" else path.removeprefix("/static/"))
            request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/workflow/requirements/document":
            request.fulfill(json={"description": source, "filename": "Requirements.pdf", "uploaded_brd_receipt": "receipt"})
        elif path == "/api/workflow/validate-requirements":
            request.fulfill(status=422, json={"detail": {"message": report["message"], "requirements_validation": report}})
        elif path == "/api/workspace/rules":
            request.fulfill(json={"business_rules": []})
        elif path == "/api/auth/profile":
            request.fulfill(json={"display_name": "Reviewer", "is_admin": False})
        else:
            request.fulfill(json={"models": [], "events": [], "history": [], "active": [], "business_rules": []})

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(accept_downloads=True)
        page.route("**/*", route)
        page.goto("http://localhost/")
        page.locator("#requirement-file").set_input_files({
            "name": "Requirements.pdf", "mimeType": "application/pdf", "buffer": b"fixture"
        })
        page.locator("#validate-requirements").click()
        panel = page.locator("#requirements-validation-report")
        playwright.expect(panel).to_contain_text("Reject a negative deposit.")
        page.locator("#preview-brd-draft").click()
        playwright.expect(page.locator("#brd-draft-text")).to_be_visible()
        playwright.expect(page.locator("#brd-draft-text")).to_have_value(
            re.compile("The quotation permits a negative deposit")
        )
        page.locator("#brd-draft-text").fill("Reviewed BRD correction")
        with page.expect_download() as download_info:
            page.locator("#download-brd-draft").click()
        download = download_info.value
        assert download.suggested_filename == "Requirements-proposed-brd.md"
        assert Path(download.path()).read_text() == "Reviewed BRD correction"
        page.locator("#file-remove").click()
        playwright.expect(panel).to_be_hidden()
        browser.close()
