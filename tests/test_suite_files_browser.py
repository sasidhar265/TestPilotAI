"""Opt-in browser regression: RUN_BROWSER_TESTS=1 pytest tests/test_suite_files_browser.py."""

import json
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.agents.context_converter_agent import ContextConverterAgent
from app.agents.reqnroll_step_definition_agent import (
    ReqnRollStepDefinitionAgent,
    StepDefinitionRequest,
)
from app.agents.test_case_validator import ValidationReport
from app.config import Settings
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
    bindings = ReqnRollStepDefinitionAgent(Settings(_env_file=None)).generate_bindings(
        StepDefinitionRequest(suite=source, validation=validation)
    )
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
        elif path == "/api/workspace/rules":
            route.fulfill(json={"business_rules": []})
        elif path == "/api/workspace/standards":
            route.fulfill(json={"automation": "Use scenario state", "feature": "No tags"})
        elif path == "/api/dashboard":
            route.fulfill(json={"active": [], "history": [], "scope": "Test workspace"})
        elif path == "/api/step-definitions/languages/bindings":
            route.fulfill(json=bindings.model_dump())
        elif path == "/api/step-definitions/languages/download":
            route.fulfill(body=b"test-zip", content_type="application/zip")
        elif path == "/api/step-definitions/languages/pack":
            pending_step_requests.append(route)
        elif path.startswith("/api/generation/") and path.endswith("/cancel"):
            route.fulfill(json={"cancelled": True})
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
        playwright.expect(page.locator("#step-definitions")).to_be_visible()
        assert paths.count("/api/step-definitions/languages/pack") == 0
        assert paths.count("/api/step-definitions/languages/bindings") == 1
        assert (
            page.locator(".step-definition-file", has=page.locator(".copy-step-definition")).count()
            == 1
        )
        page.locator("#suite-download-menu summary").click()
        with page.expect_download() as download:
            page.locator("#suite-download-cs").click()
        assert download.value.suggested_filename.endswith(".cs")
        assert "PendingStepException" in Path(download.value.path()).read_text()
        assert paths.count("/api/step-definitions/languages/pack") == 0
        page.locator("#suite-view-menu summary").click()
        page.locator("#view-csharp-pack").click()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_visible()
        playwright.expect(page.get_by_role("progressbar")).to_be_visible()
        playwright.expect(page.locator("#cs-generation-time")).not_to_have_text("00:00 elapsed")
        page.locator("#hide-cs-generation").click()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_hidden()
        page.locator("#suite-view-menu summary").click()
        page.locator("#view-csharp-pack").click()
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
        with page.expect_download() as download:
            page.locator("#download-csharp-pack").click()
        assert download.value.suggested_filename.endswith(".zip")
        assert paths.count("/api/step-definitions/languages/pack") == 1
        page.locator("#suite-download-menu summary").click()
        with page.expect_download() as download:
            page.locator("#suite-download-cs").click()
        assert download.value.suggested_filename.endswith(".cs")
        assert "PendingStepException" in Path(download.value.path()).read_text()
        assert paths.count("/api/step-definitions/languages/bindings") == 1
        page.evaluate("data => render(data)", source.model_dump(mode="json"))
        page.locator("#suite-view-menu summary").click()
        page.locator("#view-csharp-pack").click()
        playwright.expect(page.locator("#step-definitions")).to_be_visible()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_hidden()
        assert paths.count("/api/step-definitions/languages/pack") == 1
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
        playwright.expect(page.locator("#view-csharp-pack")).to_be_disabled()
        playwright.expect(page.locator("#download-csharp-pack")).to_be_disabled()
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
        page.locator("#view-csharp-pack").click()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_visible()
        page.wait_for_function("stepDefinitionTask !== null")
        # Allow the intercepted request to arrive before returning a server error.
        with page.expect_response("**/api/step-definitions/languages/pack"):
            page.wait_for_timeout(100)
            pending_step_requests.pop().fulfill(status=500, json={"detail": "Generation failed"})
        playwright.expect(page.locator("#cs-generation-message")).to_have_text("Generation failed")
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_visible()
        playwright.expect(page.locator("#cs-generation-dialog [role=progressbar]")).to_be_hidden()
        playwright.expect(page.locator("#status")).to_contain_text("Generation failed")
        page.locator("#hide-cs-generation").click()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_hidden()
        assert page.evaluate("stepDefinitionTimer === null && stepDefinitionTask === null")
        # A cancelled pack must not render or enter the cache, and can be retried.
        page.locator("#suite-view-menu summary").click()
        page.locator("#view-csharp-pack").click()
        playwright.expect(page.locator("#cancel-cs-generation")).to_be_visible()
        playwright.expect(page.locator("#hide-cs-generation")).to_have_text("Run in background")
        page.locator("#cancel-cs-generation").click()
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_hidden()
        playwright.expect(page.locator("#status")).to_have_text(
            "Automation pack generation cancelled."
        )
        assert page.evaluate("stepDefinitionTask === null && stepDefinitionRequest === null")
        assert page.evaluate("stepDefinitionTimer === null && stepDefinitionArtifact === null")
        assert any(path.endswith("/cancel") for path in paths)
        page.locator("#suite-view-menu summary").click()
        page.locator("#view-csharp-pack").click()
        playwright.expect(page.locator("#cancel-cs-generation")).to_be_enabled()
        page.wait_for_timeout(100)
        pending_step_requests.pop().fulfill(json=csharp.model_dump())
        playwright.expect(page.locator("#cs-generation-dialog")).to_be_hidden()
        playwright.expect(page.locator("#step-definitions")).to_be_visible()
        assert not errors, json.dumps(errors)
        browser.close()


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_model_picker_only_lists_available_routes() -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    state = {
        "models": [
            {"model": "codex", "display_name": "Codex CLI", "can_use": True},
            {"model": "openai", "display_name": "Unavailable API", "can_use": False},
        ],
        "fail": False,
    }

    def route_request(route):
        path = urlparse(route.request.url).path
        if path == "/" or path.startswith("/static/"):
            file = static / (path.removeprefix("/static/") if path != "/" else "index.html")
            route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/llm/models":
            route.fulfill(status=503 if state["fail"] else 200, json={"models": state["models"]})
        else:
            route.fulfill(json={})

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.route("**/*", route_request)
        page.goto("http://localhost/")
        page.locator("#description").fill("Verify the quotation API response")
        playwright.expect(page.locator("#llm-model")).to_have_value("codex")
        playwright.expect(page.locator("#llm-model option")).to_have_count(1)
        playwright.expect(page.locator("#generate")).to_be_enabled()
        state["models"] = []
        page.locator("#refresh-llm-models").click()
        playwright.expect(page.locator("#llm-model")).to_be_disabled()
        playwright.expect(page.locator("#llm-model")).to_have_text("No models available")
        playwright.expect(page.locator("#generate")).to_be_enabled()
        state["fail"] = True
        page.locator("#refresh-llm-models").click()
        playwright.expect(page.locator("#llm-model")).to_have_text("Models unavailable")
        playwright.expect(page.locator("#generate")).to_be_enabled()
        state.update(
            fail=False, models=[{"model": "codex", "display_name": "Codex CLI", "can_use": True}]
        )
        page.locator("#refresh-llm-models").click()
        playwright.expect(page.locator("#llm-model")).to_have_value("codex")
        playwright.expect(page.locator("#generate")).to_be_enabled()
        browser.close()


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_business_scenarios_and_test_case_headings_are_distinct() -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    title = (
        "Sign in with an incorrect password is rejected without creating an authenticated session"
    )
    source = Suite.model_validate(
        {
            "feature_name": "Account access",
            "test_cases": [
                {
                    "id": "TC-001",
                    "scenario_group": "Account sign-in",
                    "title": title,
                    "objective": "Verify incorrect credentials cannot grant account access.",
                    "category": "critical",
                    "priority": "P1",
                    "execution_mode": "manual",
                    "feasibility_reason": "Review the sign-in error message",
                    "steps": [
                        {
                            "action": "Enter an incorrect password",
                            "expected_result": "Sign-in rejected",
                        }
                    ],
                },
                {
                    "id": "TC-002",
                    "scenario_group": "Account sign-in",
                    "title": "Sign in with valid credentials creates a session",
                    "objective": "Verify a registered user can access their account.",
                    "category": "smoke",
                    "priority": "P1",
                    "execution_mode": "automation",
                    "feasibility_reason": "Stable sign-in API",
                    "steps": [
                        {"action": "Submit valid credentials", "expected_result": "Session created"}
                    ],
                    "gherkin": (
                        "Scenario: Sign in with valid credentials creates a session\n"
                        " Given a registered user\n When valid credentials are submitted\n"
                        " Then a session is created"
                    ),
                },
            ],
        }
    )

    def route_request(route):
        path = urlparse(route.request.url).path
        if path == "/" or path.startswith("/static/"):
            file = static / (path.removeprefix("/static/") if path != "/" else "index.html")
            route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        else:
            route.fulfill(json={"models": []})

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.route("**/*", route_request)
        page.goto("http://localhost/")
        page.evaluate("data => render(data)", source.model_dump(mode="json"))
        playwright.expect(page.locator(".scenario-label")).to_have_text("Business scenario")
        playwright.expect(page.locator(".scenario-group-heading h3")).to_have_text(
            "Account sign-in"
        )
        playwright.expect(page.locator(".scenario-group-heading > span")).to_have_text(
            "2 test cases"
        )
        playwright.expect(page.locator(".manual-case-heading small")).to_have_text(
            "Test case TC-001 · Manual"
        )
        playwright.expect(page.locator(".automation-case .case-id")).to_have_text(
            "Test case TC-002 · Automation"
        )
        playwright.expect(page.locator(".manual-case-heading strong")).to_have_text(title)
        playwright.expect(page.locator(".case-purpose")).to_contain_text("Verifies:")
        for width in (1280, 390, 320):
            page.set_viewport_size({"width": width, "height": 844})
            heading = page.locator(".manual-case-heading strong")
            assert heading.evaluate("e => getComputedStyle(e).whiteSpace") == "normal"
            assert heading.evaluate("e => e.scrollWidth <= e.clientWidth")
        page.locator(".manual-case-accordion > summary").click()
        playwright.expect(page.locator(".manual-execution")).to_be_visible()
        page.locator(".automation-case summary").click()
        playwright.expect(page.locator(".automation-case pre")).to_contain_text("Scenario:")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.evaluate("selectedCaseIds()") == ["TC-001", "TC-002"]
        page.screenshot(path="/tmp/test-case-hierarchy-mobile.png", full_page=True)
        browser.close()


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_pack_progress_ignores_stale_responses_and_preserves_failure():
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"

    def route_request(route):
        path = urlparse(route.request.url).path
        if path == "/" or path.startswith("/static/"):
            file = static / (path.removeprefix("/static/") if path != "/" else "index.html")
            route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        else:
            route.fulfill(json={"events": [], "history": [], "active": [], "models": []})

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.route("**/*", route_request)
        page.goto("http://localhost/")
        result = page.evaluate("""async () => {
          const originalFetch = window.fetch;
          let resolveOld;
          window.fetch = () => new Promise(resolve => { resolveOld = resolve; });
          resetPackFileProgress();
          packFileProgressRequest = "old";
          const pending = pollPackFileProgress("old");
          resetPackFileProgress();
          packFileProgressRequest = "new";
          resolveOld({ok: true, json: async () => ({complete: true, events: [
            {sequence: 99, action: "file_generated", status: "success",
             summary: "Generated file: old.cs"}
          ]})});
          await pending;
          const staleIgnored = packFileProgressSequence === 0 && packGeneratedFiles.size === 0;
          window.fetch = async () => ({ok: true, json: async () => ({complete: true, events: [
            {sequence: 1, action: "pack_generation", status: "failed",
             summary: "Pack generation failed"}
          ]})});
          await pollPackFileProgress("new");
          const message = $("cs-generation-current-file").textContent;
          const timerStopped = packFileProgressTimer === null;
          resetPackFileProgress();
          window.fetch = originalFetch;
          return {staleIgnored, message, timerStopped};
        }""")
        assert result == {
            "staleIgnored": True,
            "message": "Pack generation failed",
            "timerStopped": True,
        }
        browser.close()
