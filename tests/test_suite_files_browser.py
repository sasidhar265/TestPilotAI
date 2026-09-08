"""Opt-in browser regression: RUN_BROWSER_TESTS=1 pytest tests/test_suite_files_browser.py."""

import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.agents.context_converter_agent import ContextConverterAgent
from app.agents.reqnroll_step_definition_agent import ReqnRollStepDefinitionAgent
from app.agents.test_case_validator import ValidationReport
from app.models import ExportFormat
from app.models import TestSuite as Suite


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_suite_view_and_download_menus(tmp_path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    source = Suite.model_validate(
        {
            "feature_name": "Quotation API",
            "output_format": "bdd",
            "test_cases": [
                {
                    "id": "TC-001",
                    "title": "Create a quotation",
                    "objective": "Verify quote creation",
                    "category": "smoke",
                    "priority": "P1",
                    "execution_mode": "automation",
                    "feasibility_reason": "Stable API",
                    "steps": [{"action": "Submit a quotation", "expected_result": "HTTP 201"}],
                    "gherkin": 'Scenario: Create quotation\n Given a request built from "valid"\n'
                    ' When I send a "POST" request to "/quotes"\n Then the response status is 201',
                }
            ],
        }
    )
    validation = ValidationReport(
        passed=True, score=100, acceptance_criteria_total=0, acceptance_criteria_covered=0
    )
    csharp = ReqnRollStepDefinitionAgent._fallback_artifact(source.feature_name, source.test_cases)
    paths = []
    errors = []
    pending_step_requests = []
    static = Path(__file__).parents[1] / "app/static"

    def route_request(route):
        path = urlparse(route.request.url).path
        paths.append(path)
        if path == "/" or path.startswith("/static/"):
            file = static / (path.removeprefix("/static/") if path != "/" else "index.html")
            route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path.startswith("/api/context-converter/"):
            artifact = ContextConverterAgent().convert(
                Suite.model_validate(route.request.post_data_json["suite"]),
                validation,
                ExportFormat(path.rsplit("/", 1)[1]),
            )
            route.fulfill(
                body=artifact.content,
                content_type=artifact.media_type,
                headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
            )
        elif path == "/api/step-definitions/reqnroll":
            pending_step_requests.append(route)
        elif path == "/api/auth/profile":
            route.fulfill(json={"display_name": "Test Reviewer", "is_admin": False})
        else:
            route.fulfill(json={"ok": True, "events": [], "openai_model": "test"})

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route_request)
        page.goto("http://localhost/")
        page.evaluate(
            """data => {
          startLifecycleFeed = () => {}; stopLifecycleFeed = async () => {};
          validationReport = data.validation; render(data.suite);
        }""",
            {"suite": source.model_dump(mode="json"), "validation": validation.model_dump()},
        )
        page.locator(".suite-jira summary").click()
        playwright.expect(page.locator(".suite-jira")).to_have_attribute("open", "")
        page.locator("#suite-view-menu summary").click()
        playwright.expect(page.locator(".suite-jira")).not_to_have_attribute("open", "")
        page.locator("#view-feature").click()
        playwright.expect(page.locator("#feature-file-content")).to_contain_text(
            "Feature: Quotation API"
        )
        page.locator("#suite-view-menu summary").click()
        page.locator("#generate-step-definitions").click()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_visible()
        playwright.expect(page.get_by_role("progressbar")).to_be_visible()
        playwright.expect(page.locator("#cs-generation-time")).not_to_have_text("00:00 elapsed")
        page.locator("#hide-cs-generation").click()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_hidden()
        page.locator("#suite-view-menu summary").click()
        page.locator("#generate-step-definitions").click()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_visible()
        assert len(pending_step_requests) == 1
        pending_step_requests.pop().fulfill(json=csharp.model_dump())
        playwright.expect(page.locator("#step-definitions")).to_be_visible()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_hidden()
        assert page.evaluate("stepDefinitionTimer === null")
        playwright.expect(page.locator("#feature-file-view")).to_be_hidden()
        page.locator("#suite-download-menu summary").click()
        for format in ["xlsx", "csv", "pdf", "json"]:
            playwright.expect(page.locator(f"#{format}")).to_be_visible()
            playwright.expect(page.locator(f"#{format}")).to_be_disabled()
        assert "must be downloaded" in page.evaluate(
            "async () => { try { await convert('json'); } catch (e) { return e.message; } }"
        )
        with page.expect_download() as download:
            page.locator("#download-feature").click()
        assert download.value.suggested_filename.endswith(".feature")
        page.locator("#suite-download-menu summary").click()
        page.locator("#suite-download-cs").click()
        playwright.expect(page.locator("#cs-download-dialog")).to_be_visible()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_hidden()
        with page.expect_download() as download:
            page.locator("#cs-download-files button").first.click()
        assert download.value.suggested_filename.endswith(".cs")
        assert "[Binding]" in Path(download.value.path()).read_text()
        assert paths.count("/api/step-definitions/reqnroll") == 1
        page.locator("#close-cs-download").click()
        page.evaluate("data => render(data)", source.model_dump(mode="json"))
        page.locator("#suite-view-menu summary").click()
        page.locator("#generate-step-definitions").click()
        playwright.expect(page.locator("#step-definitions")).to_be_visible()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_hidden()
        assert paths.count("/api/step-definitions/reqnroll") == 1
        page.locator(".suite-jira summary").click()
        page.locator("#suite-download-menu summary").click()
        playwright.expect(page.locator(".suite-jira")).not_to_have_attribute("open", "")
        page.keyboard.press("Escape")
        page.set_viewport_size({"width": 390, "height": 844})
        page.locator("#suite-download-menu summary").click()
        bounds = page.locator("#suite-download-menu .suite-menu-options").bounding_box()
        assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
        page.screenshot(path=str(tmp_path / "suite-menus-mobile.png"), full_page=True)
        page.keyboard.press("Escape")
        playwright.expect(page.locator("#suite-download-menu")).not_to_have_attribute("open", "")
        manual = source.model_dump(mode="json")
        manual["test_cases"][0].update(execution_mode="manual", gherkin=None)
        page.evaluate("data => render(data)", manual)
        assert page.evaluate("stepDefinitionArtifact === null")
        page.locator("#suite-view-menu summary").click()
        playwright.expect(page.locator("#view-feature")).to_be_disabled()
        playwright.expect(page.locator("#generate-step-definitions")).to_be_disabled()
        for format in ["xlsx", "csv", "pdf", "json"]:
            page.locator("#suite-download-menu summary").click()
            playwright.expect(page.locator(f"#{format}")).to_be_visible()
            with page.expect_download() as download:
                page.locator(f"#{format}").click()
            assert download.value.suggested_filename.endswith("." + format)
            assert Path(download.value.path()).stat().st_size > 0
        page.evaluate("validationReport.passed = false; syncSuiteFileActions();")
        page.locator("#suite-download-menu summary").click()
        playwright.expect(page.locator("#pdf")).to_be_disabled()
        page.evaluate(
            "data => { validationReport.passed = true; "
            "data.feature_name = 'Changed API'; render(data); }",
            source.model_dump(mode="json"),
        )
        page.locator("#suite-view-menu summary").click()
        page.locator("#generate-step-definitions").click()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_visible()
        page.wait_for_function("stepDefinitionTask !== null")
        # Allow the intercepted request to arrive before returning a server error.
        with page.expect_response("**/api/step-definitions/reqnroll"):
            page.wait_for_timeout(100)
            pending_step_requests.pop().fulfill(status=500, json={"detail": "Generation failed"})
        playwright.expect(page.locator("#cs-generation-message")).to_have_text("Generation failed")
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_visible()
        playwright.expect(page.locator("#cs-generation-dialog [role=progressbar]")).to_be_hidden()
        playwright.expect(page.locator("#status")).to_contain_text("Generation failed")
        page.locator("#hide-cs-generation").click()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_hidden()
        assert page.evaluate("stepDefinitionTimer === null && stepDefinitionTask === null")
        assert not errors, json.dumps(errors)
        browser.close()
