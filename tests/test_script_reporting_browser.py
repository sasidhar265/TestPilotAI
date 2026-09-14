"""Exercise script preview/download and execution reporting through the browser."""

import io
import json
import mimetypes
import os
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.script_packs import ScriptPackRequest, build_pack


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_script_builder_and_reporting(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    data = json.loads(Path("automation/Input/ScriptPacks.Json").read_text())["jmeter"]
    data = ScriptPackRequest.model_validate(data).model_dump(mode="json")
    static = Path("app/static")
    errors = []
    history = [
        {
            "id": "run-1",
            "operation": "repository_checks",
            "status": "failed",
            "started_at": "2026-09-13T12:00:00Z",
            "duration_ms": 2400,
            "details": {
                "passed": 2,
                "failed": 1,
                "skipped": 0,
                "project": "Repository project",
                "test_results": [
                    {"name": "Health probe", "status": "Failed", "duration": "00:00:01"}
                ],
            },
        },
        {
            "id": "run-0",
            "operation": "repository_checks",
            "status": "passed",
            "started_at": "2026-09-12T12:00:00Z",
            "duration_ms": 2100,
            "details": {"passed": 3, "failed": 0, "skipped": 0},
        },
    ]

    def route(r):
        path = urlparse(r.request.url).path
        if path == "/" or path.startswith("/static/"):
            file = static / ("index.html" if path == "/" else path.removeprefix("/static/"))
            r.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path.startswith("/api/script-packs/"):
            pack = build_pack(ScriptPackRequest.model_validate(r.request.post_data_json))
            if path.endswith("generate"):
                r.fulfill(json=pack.model_dump())
            else:
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w") as archive:
                    for file in pack.files:
                        archive.writestr(file.path, file.content)
                r.fulfill(body=output.getvalue(), content_type="application/zip")
        elif path == "/api/automation/history":
            r.fulfill(json={"active": [], "history": history, "scope": "Repository test history"})
        else:
            r.fulfill(
                json={
                    "ok": True,
                    "events": [],
                    "complete": True,
                    "business_rules": [],
                    "display_name": "Reviewer",
                    "models": [],
                }
            )

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://localhost/")
        page.evaluate("data => { validationReport=data.validation; render(data.suite); }", data)
        page.locator("#select-all").click()
        page.locator("#open-script-pack").click()
        page.locator('[data-field="path"]').fill("/api/health")
        page.locator('[data-field="expected_status"]').fill("200")
        page.locator('[data-field="max_response_ms"]').fill("5000")
        page.locator("#generate-script-pack").click()
        pw.expect(page.locator("#script-pack-status")).to_contain_text("1 cases mapped")
        pw.expect(page.locator("#script-pack-content")).to_contain_text("HTTPSamplerProxy")
        with page.expect_download() as result:
            page.locator("#download-script-pack").click()
        result.value.save_as(tmp_path / "jmeter.zip")
        with zipfile.ZipFile(tmp_path / "jmeter.zip") as archive:
            assert "Features/performance.jmx" in archive.namelist()
        for target in ("sql", "oracle"):
            page.locator("#script-pack-target").select_option(target)
            pw.expect(page.locator("#script-pack-preview")).to_be_hidden()
            page.locator('[data-field="query"]').fill(
                "SELECT 1" if target == "sql" else "SELECT 1 FROM dual"
            )
            page.locator('[data-field="expected_rows"]').fill("1")
            page.locator("#generate-script-pack").click()
            pw.expect(page.locator("#script-pack-content")).to_contain_text("actual_rows")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.locator("#script-pack-dialog").evaluate(
            "el => el.scrollWidth <= el.clientWidth"
        )
        page.screenshot(path=str(tmp_path / "scripts-mobile.png"), full_page=True)
        page.locator("#close-script-pack").click()
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator('.primary-nav a[href="/progress"]').click()
        pw.expect(page.locator("#bdd-insight")).to_contain_text(
            "1 failing test requires investigation"
        )
        pw.expect(page.locator("#bdd-test-results")).to_contain_text("Health probe")
        page.locator("#bdd-status-filter").select_option("failed")
        pw.expect(page.locator("#bdd-history-count")).to_have_text("1")
        with page.expect_download() as result:
            page.locator("#export-run-history").click()
        result.value.save_as(tmp_path / "history.csv")
        csv = (tmp_path / "history.csv").read_text()
        assert "run-1" in csv and "run-0" not in csv
        page.screenshot(path=str(tmp_path / "report-desktop.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.evaluate("document.documentElement.dataset.theme='dark'")
        page.screenshot(path=str(tmp_path / "report-mobile-dark.png"), full_page=True)
        history[0]["status"] = "error"
        page.locator("#refresh-dashboard").click()
        pw.expect(page.locator("#bdd-insight")).to_contain_text("runner error")
        history.clear()
        page.locator("#refresh-dashboard").click()
        pw.expect(page.locator("#bdd-insight")).to_contain_text("Awaiting the first execution")
        pw.expect(page.locator("#export-run-history")).to_be_disabled()
        assert not errors
        browser.close()
