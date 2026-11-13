"""Requirements remain usable after removing the separate website inspection UI."""

import os
from urllib.parse import urlparse

import pytest
from test_mobile_navigation_browser import mobile_route


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_requirements_without_website_inspection_section():
    pw = pytest.importorskip("playwright.sync_api")
    requirements = "Verify that the approved help link opens https://example.com/."
    requests = []
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route(request):
            path = urlparse(request.request.url).path
            if path == "/api/workflow/intent":
                request.fulfill(
                    json={
                        "workflow": "stories",
                        "summary": "Create explicitly requested user stories.",
                        "questions": [],
                        "generation_target": "manual",
                        "testing_type": "api",
                    }
                )
            elif path == "/api/workflow/stories":
                requests.append(request.request.post_data_json)
                request.fulfill(
                    status=503, json={"detail": "Provider unavailable in this UI fixture"}
                )
            else:
                mobile_route(request)

        page.route("**/*", route)
        page.goto("http://localhost/")
        pw.expect(page.locator("#website-source")).to_have_count(0)
        pw.expect(page.locator("#inspect-website")).to_have_count(0)
        page.locator("#description").fill(requirements)
        page.locator("#generate").click()
        page.wait_for_function(
            "document.querySelector('#status').textContent.includes('Provider unavailable')"
        )
        assert requests[0]["description"] == requirements
        assert requests[0]["website_source_text"] is None
        assert requests[0]["website_source_receipt"] is None
        assert not errors
        browser.close()


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("generation_fails", [False, True])
def test_framework_prompt_uses_direct_agent_route(generation_fails):
    pw = pytest.importorskip("playwright.sync_api")
    prompt = (
        "Build a C# automation framework for 'https://careerpilot-nrn7.onrender.com' "
        "using Selenium, C#, and BDD in a page object model. "
        "Segregate regression, sanity and smoke tests."
    )
    requests = []
    interpretations = []
    wrong_routes = []
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route(request):
            path = urlparse(request.request.url).path
            if path == "/api/auth/profile":
                request.fulfill(
                    json={
                        "username": "framework-reviewer",
                        "display_name": "Reviewer",
                        "is_admin": True,
                    }
                )
            elif path == "/api/workflow/intent":
                interpretations.append(request.request.post_data_json)
                request.fulfill(
                    json={
                        "workflow": "website-framework",
                        "summary": "Build the requested Selenium framework.",
                        "questions": [],
                        "generation_target": "automation",
                        "testing_type": "api",
                    }
                )
            elif path == "/api/agent/run":
                requests.append(request.request.post_data_json)
                if generation_fails:
                    request.fulfill(status=422, json={"detail": "Website could not be inspected"})
                else:
                    request.fulfill(
                        json={
                            "workflow": "prompt-result",
                            "intent": {
                                "workflow": "website-framework",
                                "summary": "Build the requested framework.",
                                "questions": [],
                            },
                            "source_request": requests[-1],
                            "result": {
                                "workflow": "website-framework",
                                "target_url": "https://careerpilot-nrn7.onrender.com/",
                                "language": "csharp",
                                "framework": "ReqnRoll",
                                "automation_tool": "Selenium",
                                "design_pattern": "Page Object Model + PageFactory",
                                "target_framework": "net10.0",
                                "files": [
                                    {
                                        "path": "README.md",
                                        "content": "# CareerPilot Selenium framework",
                                    },
                                    {
                                        "path": "Pages/HomePage.cs",
                                        "content": "public sealed class HomePage { }",
                                    },
                                    {
                                        "path": "Features/README.md",
                                        "content": "Feature folder notes",
                                    },
                                    {
                                        "path": "Features/Smoke/Smoke.feature",
                                        "content": "Feature: Smoke website readiness",
                                    },
                                    {
                                        "path": "StepDefinitions/README.md",
                                        "content": "Bindings folder notes",
                                    },
                                    {
                                        "path": "StepDefinitions/WebsiteStepDefinition.cs",
                                        "content": "public sealed class WebsiteStepDefinition { }",
                                    },
                                ],
                                "stack": "Selenium / C# / ReqnRoll BDD / page object model",
                                "scenario_counts": {"smoke": 1, "sanity": 1, "regression": 1},
                                "observations": "Observed Careers page.",
                                "file_names": ["Automation.csproj"],
                                "page_objects": ["Pages/HomePage.cs"],
                                "test_suites": [
                                    {
                                        "name": name,
                                        "scenario_count": 1,
                                        "feature_file": f"Features/{name}/{name}.feature",
                                        "scenarios": [f"{name.upper()}-001 - Home page check"],
                                        "command": f"dotnet test --filter TestCategory={name}",
                                    }
                                    for name in ["Smoke", "Sanity", "Regression"]
                                ],
                                "limitations": ["Tests have not run."],
                                "archive_base64": "UEs=",
                                "filename": "website-automation.zip",
                            },
                        }
                    )
            elif path in {"/api/workflow/stories", "/api/workflow/requirements/website"}:
                wrong_routes.append(path)
                request.fulfill(status=500, json={"detail": "Wrong workflow"})
            else:
                mobile_route(request)

        page.route("**/*", route)
        page.goto("http://localhost/")
        page.locator("#description").fill(prompt)
        page.locator("#generate").click()
        if generation_fails:
            pw.expect(page.locator("#status")).to_contain_text("Website could not be inspected")
            pw.expect(page.locator("#website-framework-result")).to_have_count(0)
            pw.expect(page.locator("#generation-next-step")).to_contain_text(
                "Website could not be inspected"
            )
            page.locator("#generate").click()
            pw.expect(page.locator("#status")).to_contain_text("Website could not be inspected")
            pw.expect(page.locator("#generate")).to_be_enabled()
            assert len(requests) == 2
        else:
            pw.expect(page.locator("#website-framework-result")).to_contain_text(
                "Execution: not run"
            )
            pw.expect(
                page.get_by_role("link", name="Download automation framework (.zip)")
            ).to_be_visible()
            for category in ["Smoke", "Sanity", "Regression"]:
                pw.expect(page.get_by_role("heading", name=f"{category} · 1 test")).to_be_visible()
            pw.expect(page.locator("#website-framework-result")).to_contain_text(
                "Pages/HomePage.cs"
            )
            pw.expect(page).to_have_url("http://localhost/?view=automation")
            pw.expect(
                page.locator("#automation-workspace #website-framework-result")
            ).to_be_visible()
            pw.expect(page.locator("#automation-language")).to_have_value("csharp")
            pw.expect(page.locator("#automation-language")).to_be_disabled()
            for control, value in {
                "generated-pack-framework": "ReqnRoll",
                "generated-pack-tool": "Selenium",
                "generated-pack-pattern": "Page Object Model + PageFactory",
                "generated-pack-runtime": "net10.0",
            }.items():
                pw.expect(page.locator(f"#{control}")).to_have_value(value)
                pw.expect(page.locator(f"#{control}")).to_be_disabled()
            page.locator('[data-suite-action="view-feature"]').click()
            pw.expect(page.locator("#generated-framework-file-content")).to_have_text(
                "Feature: Smoke website readiness"
            )
            page.locator('[data-suite-action="generate-step-definitions"]').click()
            pw.expect(page.locator("#generated-framework-file-content")).to_have_text(
                "public sealed class WebsiteStepDefinition { }"
            )
            with page.expect_download() as saved:
                page.locator('[data-suite-action="download-csharp-pack"]').click()
            assert saved.value.suggested_filename == "website-automation.zip"
            page.locator("#generated-framework-file").select_option("1")
            pw.expect(page.locator("#generated-framework-file-content")).to_have_text(
                "public sealed class HomePage { }"
            )
            page.reload()
            pw.expect(
                page.locator("#automation-workspace #website-framework-result")
            ).to_be_visible()
            pw.expect(page.locator("#automation-language")).to_be_disabled()
            assert len(requests) == 1
            page.get_by_role("link", name="Requirements", exact=True).click()
            page.locator("#description").fill("Changed requirements for another task")
            pw.expect(page.locator("#website-framework-result")).to_have_count(0)
            pw.expect(page.locator("#automation-language")).to_be_enabled()
            pw.expect(page.locator("#generated-pack-configuration")).to_be_hidden()
        assert len(interpretations) == 1
        assert requests[0]["description"] == prompt
        assert not wrong_routes
        assert not errors
        browser.close()


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_ambiguous_prompt_asks_before_starting_generation():
    pw = pytest.importorskip("playwright.sync_api")
    downstream = []
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()

        def route(request):
            path = urlparse(request.request.url).path
            if path == "/api/workflow/intent":
                request.fulfill(
                    json={
                        "workflow": "clarify",
                        "summary": "You supplied a search requirement without a requested output.",
                        "questions": ["Would you like test cases, stories or a review?"],
                        "generation_target": "auto",
                        "testing_type": "api",
                    }
                )
            elif path in {"/api/agent/run", "/api/workflow/stories", "/api/workflow/ba-review"}:
                downstream.append(path)
                request.fulfill(status=500, json={"detail": "Unexpected generation"})
            else:
                mobile_route(request)

        page.route("**/*", route)
        page.goto("http://localhost/")
        page.locator("#description").fill("A user can search for available roles.")
        page.get_by_role("button", name="Run task").click()
        pw.expect(page.locator("#task-interpretation")).to_contain_text(
            "Would you like test cases, stories or a review?"
        )
        pw.expect(page.locator("#generate")).to_be_enabled()
        assert not downstream
        browser.close()
