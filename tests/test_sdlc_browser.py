"""Opt-in SDLC UI checks with a persistent store and isolated browser transport."""

import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

from app.config import Settings
from app.roles import capabilities
from app.services.project_lifecycle import ProjectLifecycle
from app.services.project_work_items import ProjectWorkItems
from app.services.sdlc import SDLCStore
from app.services.sdlc_delivery import capabilities as sdlc_capabilities


@pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("uploaded_brd", [False, True])
def test_sdlc_project_review_and_reload(tmp_path, uploaded_brd):
    playwright = pytest.importorskip("playwright.sync_api")
    store = SDLCStore(tmp_path / "memory.db")
    static = Path(__file__).parents[1] / "app/static"
    errors = []

    def route_request(route):
        path = urlparse(route.request.url).path
        if path in {"/", "/sdlc"} or path.startswith("/static/"):
            file = static / ("index.html" if path in {"/", "/sdlc"} else path[8:])
            route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/auth/profile":
            route.fulfill(
                json={
                    "username": "reviewer",
                    "display_name": "Reviewer",
                    "role": "admin",
                    "is_admin": True,
                    "capabilities": capabilities("admin"),
                }
            )
        elif path == "/api/sdlc/agents":
            route.fulfill(
                json=sdlc_capabilities(Settings(_env_file=None, runtime_config_path=None))
            )
        elif path.startswith("/api/sdlc"):
            parts = path.removeprefix("/api/sdlc/").split("/")
            payload = route.request.post_data_json if route.request.method == "POST" else None
            if parts == ["projects"]:
                result = (
                    store.create(payload["name"], "reviewer")
                    if payload
                    else store.projects("reviewer")
                )
            elif len(parts) == 3 and parts[2] == "lifecycle":
                result = ProjectLifecycle(store).snapshot(parts[1], "reviewer", "admin")
            elif len(parts) == 3 and parts[2] == "work-items":
                result = ProjectWorkItems(store).list(parts[1], "reviewer")
            elif parts == ["queue"]:
                result = [
                    dict(
                        project=item,
                        lifecycle=ProjectLifecycle(store).snapshot(item["id"], "reviewer", "admin"),
                    )
                    for item in store.projects("reviewer")
                ]
            elif parts[0] == "runs":
                result = store.run(parts[1], "reviewer")
            elif len(parts) == 3 and parts[2] == "runs":
                source = next(
                    item
                    for item in store.snapshot(parts[1], "reviewer")["artifacts"]
                    if item["stage"] == "requirements-input"
                )
                assert payload == {"requirements_version": source["version"], "target": "tested"}
                request = source["content"]["source_request"]
                if uploaded_brd:
                    assert request["uploaded_brd_receipt"] == "browser-test-upload-receipt"
                    assert request["description"].count("Approved BRD document requirements") == 1
                result = store.create_run(
                    parts[1],
                    "reviewer",
                    {
                        **payload,
                        "brief": request["description"],
                        "source_request": request,
                        "constraints": request["additional_context"],
                        "llm_model": request["llm_model"],
                    },
                )
                store.save(
                    parts[1],
                    "reviewer",
                    "design",
                    {"document": "API contract uses the approved quotation payload"},
                    0,
                    [{"stage": "requirements-input", "version": source["version"]}],
                    run_id=result["id"],
                )
                result = store.update_run(
                    result["id"],
                    "reviewer",
                    status="blocked",
                    stage="development",
                    completed=["planning", "requirements", "design"],
                    artifacts={
                        "planning": {
                            "document": "Simulated agent plan for UI verification",
                            "tasks": [],
                        }
                    },
                    error="Configure SDLC_BUILD_COMMAND before implementation",
                )
                store.run_event(
                    result["id"],
                    "reviewer",
                    "development",
                    "gate_blocked",
                    "blocked",
                    "Build configuration is required",
                )
            elif len(parts) == 2:
                result = store.snapshot(parts[1], "reviewer")
            elif parts[-1] == "reviews":
                result = store.review(
                    parts[1],
                    "reviewer",
                    parts[3],
                    payload["version"],
                    payload["decision"],
                    payload["comment"],
                )
            else:
                if parts[3] == "requirements-input":
                    payload["content"]["document"] = payload["content"]["source_request"][
                        "description"
                    ]
                result = store.save(
                    parts[1],
                    "reviewer",
                    parts[3],
                    payload["content"],
                    payload["base_version"],
                    payload["links"],
                )
            route.fulfill(json=result)
        elif path == "/api/workflow/requirements/document":
            route.fulfill(
                json={
                    "description": "Approved BRD document requirements",
                    "uploaded_brd_receipt": "browser-test-upload-receipt",
                }
            )
        elif path == "/api/llm/models":
            route.fulfill(json={"models": []})
        elif path == "/api/workspace/rules":
            route.fulfill(json={"business_rules": []})
        elif path == "/api/workspace/standards":
            route.fulfill(json={"automation": "", "feature": ""})
        else:
            route.fulfill(json={})

    with playwright.sync_playwright() as runner:
        browser = runner.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route_request)
        page.goto("http://workspace/")
        page.locator("#sdlc-name").fill("Quotation SDLC")
        page.locator("#sdlc-create button").click()
        page.wait_for_function("!document.querySelector('#sdlc-start-delivery').disabled")
        page.locator("#description").fill("Persistent quotation requirements from the approved BRD")
        if uploaded_brd:
            page.locator('input[type="file"]').first.set_input_files(
                {
                    "name": "requirements.docx",
                    "mimeType": (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    ),
                    "buffer": b"Approved BRD document requirements",
                }
            )
        assert page.locator("#requirements-options").get_attribute("open") is None
        assert page.locator("#sdlc-target").is_hidden()
        page.locator("#requirements-options > summary").click()
        assert page.locator("#sdlc-target").is_visible()
        page.locator("#sdlc-constraints").fill("Use the approved quotation API contract")
        page.locator("#sdlc-target").select_option("tested")
        page.locator("#sdlc-save-requirements").click()
        page.wait_for_function(
            "document.querySelector('#sdlc-requirements-status').textContent.includes('v1 saved')"
        )
        page.reload()
        expected_source = (
            "Approved BRD document requirements" if uploaded_brd else "Persistent quotation"
        )
        page.wait_for_function(
            "expected => document.querySelector('#description').value.includes(expected)",
            arg=expected_source,
        )
        assert (
            page.locator("#sdlc-constraints").input_value()
            == "Use the approved quotation API contract"
        )
        page.locator("#sdlc-start-delivery").click()
        page.wait_for_function(
            "document.querySelector('#sdlc-run-status').textContent.includes('blocked')"
        )
        assert page.locator(".sdlc-agent-card").count() == 7
        assert page.locator(".sdlc-agent-card.passed").count() == 3
        assert "SDLC_BUILD_COMMAND" in page.locator("#sdlc-run-error").inner_text()
        assert page.locator("#sdlc-resume-run").is_visible()
        assert page.locator("#sdlc-brief").count() == 0
        assert page.locator("#sdlc-create").is_hidden()
        assert page.locator(".sdlc-source-baseline").get_attribute("open") is None
        assert (
            page.locator("#sdlc-project").get_attribute("aria-describedby") == "sdlc-project-help"
        )
        page.locator("#sdlc-create-panel summary").click()
        assert page.locator("#sdlc-create").is_visible()
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.screenshot(path="/tmp/sdlc-agent-cockpit.png", full_page=True)
        page.reload()
        page.wait_for_function(
            "document.querySelector('#sdlc-run-status').textContent.includes('blocked')"
        )
        assert page.locator(".sdlc-agent-card.blocked").count() == 1
        navigation = page.locator("#sdlc-navigation")
        assert navigation.locator('a[href="/progress"]').count() == 1
        assert navigation.locator('a[href="/?view=test-cases"]').count() == 1
        assert page.get_by_role("button", name="Quality workspace", exact=True).count() == 0
        navigation.locator(".nav-specialist-tools > summary").click()
        navigation.locator('a[href="/sdlc?stage=design"]').click()
        assert page.locator("h1").inner_text() == "Architecture"
        assert navigation.locator('[aria-current="page"]').count() == 1
        assert page.locator("#sdlc-stage-title").inner_text() == "Design"
        assert page.locator("#sdlc-document").get_attribute("readonly") is not None
        assert page.locator("#sdlc-save").is_hidden()
        assert page.locator("#sdlc-template").is_hidden()
        assert (
            page.locator("#sdlc-document").input_value()
            == "API contract uses the approved quotation payload"
        )
        assert "Requirements v2" in page.locator("#sdlc-source-summary").inner_text()
        assert page.locator("#sdlc-links").input_value() == "requirements-input:2"
        page.reload()
        page.wait_for_function(
            "document.querySelector('#sdlc-stage-title').textContent === 'Design'"
        )
        assert navigation.locator('[aria-current="page"]').count() == 1
        assert not errors
        browser.close()
