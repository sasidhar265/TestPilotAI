"""RUN_BROWSER_TESTS=1 pytest tests/test_suite_review_browser.py -q"""

import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("mode", ["manual", "automation"])
def test_review_regeneration_preserves_source_and_handles_failure_and_cancel(mode):
    playwright = pytest.importorskip("playwright.sync_api")
    static = Path(__file__).parents[1] / "app/static"
    source = {
        "description": "Original requirement: users sign in securely",
        "generation_target": mode,
        "manual_testing_type": "api",
        "llm_model": "auto-fallback",
        "output_format": "bdd" if mode == "automation" else "normal",
        "business_rules": [],
    }
    suite = {
        "feature_name": "Account access",
        "assumptions": [],
        "coverage_notes": [],
        "generation_source": "copilot",
        "test_cases": [
            {
                "id": "TC-001",
                "title": "Valid login",
                "scenario_group": "Account access",
                "objective": "Verify sign in",
                "execution_mode": mode,
                "category": "smoke",
                "priority": "P1",
                "preconditions": [],
                "test_data": [],
                "feasibility_reason": "Observable response",
                "acceptance_criteria_covered": [],
                "steps": [{"action": "Sign in", "expected_result": "Access granted"}],
                "gherkin": (
                    "Scenario: Sign in\n Given an account\n"
                    " When signing in\n Then access is granted"
                )
                if mode == "automation"
                else None,
            }
        ],
    }
    validation = {"passed": True, "score": 100}
    reviews, generations, pending, errors = [], [], [], []

    def route_request(route):
        path = urlparse(route.request.url).path
        if path == "/" or path.startswith("/static/"):
            file = static / (path.removeprefix("/static/") if path != "/" else "index.html")
            route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/reviews":
            reviews.append(route.request.post_data_json)
            route.fulfill(json={"review_id": "saved-review", "status": "saved"})
        elif path == "/api/agent/run":
            generations.append(route.request.post_data_json)
            pending.append(route)
        elif path.endswith("/cancel"):
            route.fulfill(json={"cancelled": True})
        elif path == "/api/llm/models":
            route.fulfill(
                json={
                    "models": [
                        {"model": "auto-fallback", "display_name": "Automatic", "can_use": True}
                    ]
                }
            )
        else:
            route.fulfill(json={"events": []})

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.route("**/*", route_request)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://localhost/")
        page.evaluate(
            """data => {
            startLifecycleFeed = () => {}; stopLifecycleFeed = async () => {};
            reviewSourceRequest = data.source; validationReport = data.validation;
            render(data.suite);
        }""",
            {"source": source, "suite": suite, "validation": validation},
        )
        page.locator("#description").fill(
            "Changed input must not replace the reviewed requirements"
        )
        playwright.expect(page.locator("#case-review-panel-0")).to_be_hidden()
        page.get_by_role("button", name="Review TC-001", exact=True).click()
        playwright.expect(page.locator("#case-review-panel-0")).to_be_visible()
        page.get_by_role("button", name="Review TC-001", exact=True).click()
        playwright.expect(page.locator("#case-review-panel-0")).to_be_hidden()
        page.get_by_role("button", name="Review TC-001", exact=True).click()
        comments = "add a precise expected rejection for an invalid password"
        page.locator("#case-review-comments-0").fill(comments)
        page.locator("#case-review-panel-0 .save-case-review").click()
        playwright.expect(page.locator("#case-review-status-0")).to_contain_text("Review saved")
        page.wait_for_function(
            "document.querySelector('#case-review-panel-0 .save-case-review')"
            ".textContent === 'Regenerating…'"
        )
        page.wait_for_timeout(100)
        assert reviews[0]["request"] == source
        assert reviews[0]["comments"] == comments
        assert reviews[0]["test_case_id"] == "TC-001"
        assert generations[0] == source
        assert reviews[0]["suite"]["test_cases"][0]["execution_mode"] == mode
        pending.pop().fulfill(status=503, json={"detail": "Provider offline"})
        playwright.expect(page.locator("#case-review-status-0")).to_contain_text(
            "Review saved to knowledge. Provider offline"
        )
        playwright.expect(page.locator("#case-review-comments-0")).to_have_value(comments)
        assert page.evaluate("suite.test_cases[0].title") == "Valid login"
        page.locator("#case-review-panel-0 .save-case-review").click()
        playwright.expect(page.locator("#case-review-panel-0 .save-case-review")).to_have_text(
            "Regenerating…"
        )
        page.wait_for_timeout(100)
        suite["test_cases"][0]["title"] = "Invalid password is rejected"
        pending.pop().fulfill(
            json={"suite": suite, "validation": validation, "source_request": source}
        )
        playwright.expect(page.locator("#case-review-status-0")).to_contain_text(
            "Updated 1 test cases"
        )
        playwright.expect(page.locator("#review-state")).to_have_text("Review required")
        playwright.expect(page.locator("#case-review-comments-0")).to_have_value("")
        assert page.evaluate("stepDefinitionArtifact === null")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#case-review-comments-0").fill("Also add the locked account condition")
        page.locator("#case-review-panel-0 .save-case-review").click()
        playwright.expect(page.locator("#case-review-panel-0 .save-case-review")).to_have_text(
            "Regenerating…"
        )
        page.locator("#cancel-generation-overlay").click()
        playwright.expect(page.locator("#case-review-status-0")).to_contain_text(
            "Review saved to knowledge. Regeneration cancelled."
        )
        assert page.evaluate("suite.test_cases[0].title") == "Invalid password is rejected"
        assert not errors, errors
        browser.close()
