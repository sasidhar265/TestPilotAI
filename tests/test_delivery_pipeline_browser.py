"""Delivery views share one selected run and filter output by authoritative workflow groups."""

import json
import os
from pathlib import Path

import pytest
from test_project_selection_browser import selection_browser as selection_browser

from app.lifecycle_workflow import PHASES

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check"
)


def choose_fixture_project(page, store):
    project = store.create("Delivery pipeline browser fixture", "reviewer")["id"]
    page.add_init_script(
        "sessionStorage.setItem('sdlc-active-project:reviewer', " + json.dumps(project) + ")"
    )
    return project


def visible_stages(page):
    return page.locator(".sdlc-agent-card:visible").evaluate_all(
        "elements => elements.map(item => item.dataset.stage)"
    )


def test_every_workflow_has_contextual_pipeline_and_keeps_human_actions_separate(selection_browser):
    page, store, _ = selection_browser
    choose_fixture_project(page, store)
    mutations, errors = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "request",
        lambda request: (
            mutations.append(request.url)
            if request.method == "POST" and "/artifacts/workflow" not in request.url
            else None
        ),
    )
    page.goto("http://localhost/sdlc")
    for phase in PHASES:
        page.locator(f"#sdlc-phase-{phase['id']}").click()
        assert page.locator(".workflow-pipeline-summary").is_visible()
        assert page.locator(".sdlc-workflow-views").count() == 0
        if phase["id"] == "business-approval":
            # This fixture has no reviewed BRD or BA handoff, so child links stay gated.
            assert page.locator("#sdlc-view-progress").is_hidden()
            assert page.locator("#ba-review-navigation").count() == 0
            page.evaluate(
                "window.navigateWorkspace('/sdlc?phase=business-approval&view=pipeline', false)"
            )
            page.locator(".sdlc-agent-card:visible").first.wait_for()
        else:
            page.locator("#sdlc-view-progress").click()
        assert "view=pipeline" in page.url
        assert f"phase={phase['id']}" in page.url
        expected = phase["agent_stages"] or ["requirements"]
        assert visible_stages(page) == expected
        if phase["id"] != "business-approval":
            assert "Back to" in page.locator("#sdlc-view-progress").inner_text()
        assert page.locator("#project-lifecycle").is_hidden()
        assert page.locator("#sdlc-step-panel").is_hidden()
        if phase["id"] == "business-approval":
            page.evaluate("window.navigateWorkspace('/sdlc?phase=business-approval', false)")
        else:
            page.locator("#sdlc-view-progress").click()
        assert page.locator("#sdlc-step-panel").is_visible()
        assert page.locator("#sdlc-agent-tools").is_hidden()
    assert not mutations
    assert not errors


def test_overview_and_scoped_pipeline_preserve_run_activity_and_evidence(selection_browser):
    page, store, _ = selection_browser
    project = choose_fixture_project(page, store)
    store.save(project, "reviewer", "requirements-input", {"document": "Synthetic source"}, 0, [])
    run = store.create_run(project, "reviewer", {"requirements_version": 1, "target": "tested"})
    store.update_run(
        run["id"],
        "reviewer",
        status="blocked",
        stage="development",
        completed=["planning", "requirements", "design"],
        error="Synthetic fixture: build configuration requires review",
        artifacts={
            "development": {
                "document": "Synthetic development output for UI filtering only",
                "revision": "fixture-revision",
                "files": [],
                "build": {"exit_code": 1},
                "review": {"passed": False},
            }
        },
    )
    store.run_event(
        run["id"], "reviewer", "development", "fixture", "blocked", "Synthetic development blocker"
    )
    store.run_event(
        run["id"], "reviewer", "testing", "fixture", "waiting", "Synthetic testing activity"
    )
    page.goto("http://localhost/sdlc?view=pipeline")
    page.locator(".sdlc-agent-card.blocked").wait_for()
    assert len(visible_stages(page)) == 7
    assert page.locator("h1").inner_text() == "Delivery pipeline"
    assert page.locator("#sdlc-pipeline-link").get_attribute("aria-current") == "page"
    assert "fixture-revision" in page.locator("#sdlc-run-evidence").inner_text()
    assert "Synthetic development blocker" in page.locator("#sdlc-run-events").inner_text()
    assert page.locator("#sdlc-resume-run").is_visible()
    page.locator("#sdlc-phase-qa").click()
    assert "Quality Engineering Agent" in page.locator("#workflow-pipeline-agents").inner_text()
    page.locator("#sdlc-view-progress").click()
    assert visible_stages(page) == ["testing"]
    assert "Quality assurance" in page.locator("h1").inner_text()
    assert "Synthetic testing activity" in page.locator("#sdlc-run-events").inner_text()
    assert "Synthetic development blocker" not in page.locator("#sdlc-run-events").inner_text()
    assert "fixture-revision" not in page.locator("#sdlc-run-evidence").inner_text()
    assert "Requirements v1" in page.locator("#sdlc-pipeline-scope").inner_text()
    page.reload()
    page.locator('.sdlc-agent-card[data-stage="testing"]').wait_for()
    assert visible_stages(page) == ["testing"]
    page.go_back()
    page.locator(".workflow-pipeline-summary").wait_for()
    page.go_forward()
    page.locator('.sdlc-agent-card[data-stage="testing"]').wait_for()
    assert visible_stages(page) == ["testing"]
    for width in (390, 1440):
        page.set_viewport_size({"width": width, "height": 1000})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=f"/tmp/delivery-pipeline-{width}.png", full_page=True)
    page.locator("#sdlc-pipeline-overview").click()
    assert len(visible_stages(page)) == 7
    page.locator("#sdlc-documents-link").click()
    assert page.locator(".sdlc-progress-navigation").is_hidden()
    assert page.locator("#sdlc-agent-tools").is_hidden()
    page.wait_for_function(
        "document.querySelector('#sdlc-stage-title').textContent === 'Saved BRD'"
    )
    assert page.locator("#sdlc-document").input_value() == "Synthetic source"
    page.locator("#sdlc-history summary").first.click()
    with page.expect_download() as downloaded:
        page.get_by_role("button", name="Download Saved BRD v1", exact=True).click()
    assert downloaded.value.suggested_filename == "requirements-input-v1.txt"
    assert Path(downloaded.value.path()).read_text() == "Synthetic source"
    page.locator('[data-sdlc-stage="planning"]').click()
    assert "view=documents" in page.url
    page.locator("#sdlc-document-empty").wait_for()
    assert (
        "No planning document has been saved" in page.locator("#sdlc-document-empty").inner_text()
    )
    assert page.locator("#sdlc-document").is_hidden()
    assert page.locator("#sdlc-history").inner_text() == "No saved versions for planning yet."
    page.reload()
    page.locator("#sdlc-document-empty").wait_for()
    assert page.locator("#sdlc-stage-title").inner_text() == "Planning"


def test_workflow_panel_is_on_right_and_stacks_below_on_mobile(selection_browser):
    page, store, _ = selection_browser
    choose_fixture_project(page, store)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://localhost/sdlc?phase=requirements")
    panel = page.locator("aside.workflow-pipeline-summary")
    panel.wait_for()
    assert panel.locator("#agent-workflow-title").inner_text() == "Requirements activity"
    assert panel.locator("#agent-workflow-title").is_visible()
    assert panel.locator("#workflow-pipeline-heading").is_hidden()
    assert panel.locator("#workflow-pipeline-status").is_hidden()
    assert panel.locator("#workflow-pipeline-agents").is_hidden()
    for width in (1440, 1280, 768, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        stage = page.locator(".sdlc-workspace").bounding_box()
        workflow = panel.bounding_box()
        if width >= 1280:
            assert workflow["x"] >= stage["x"] + stage["width"] + 20
            assert abs(workflow["y"] - stage["y"]) <= 1
        else:
            assert workflow["y"] >= stage["y"] + stage["height"]
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=f"/tmp/right-workflow-panel-{width}.png", full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.locator("#sdlc-phase-qa").click()
    assert panel.locator("#workflow-pipeline-heading").is_visible()
    assert page.locator("#sdlc-step-heading").inner_text() == "Quality assurance"
    assert panel.locator('a[aria-current="page"]').get_attribute("href") == "/sdlc?phase=qa"
    assert panel.locator('li[data-current="true"]').get_attribute("data-phase") == "requirements"
    page.reload()
    panel.locator('a[aria-current="page"]').wait_for()
    assert panel.locator('a[aria-current="page"]').get_attribute("href") == "/sdlc?phase=qa"
    assert not errors
