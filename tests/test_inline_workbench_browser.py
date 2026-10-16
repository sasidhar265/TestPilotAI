"""UI interactions use real local stores with explicitly synthetic AI/evidence fixtures."""

import json
import os
from urllib.parse import urlparse

import pytest
from test_mobile_navigation_browser import mobile_route
from test_project_lifecycle import item, reach

from app.roles import capabilities
from app.sdlc_routes import AnnotationInput, WorkItemInput
from app.services.project_lifecycle import ProjectLifecycle
from app.services.project_reviews import ProjectReviews
from app.services.project_work_items import ProjectWorkItems
from app.services.sdlc import SDLCStore


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize(
    "activity",
    ["suggestion", "defect", "traceability", "product_owner", "developer", "release_manager"],
)
def test_contextual_suggestion_draft_and_linked_defect_persist(tmp_path, activity):
    pw = pytest.importorskip("playwright.sync_api")
    store = SDLCStore(tmp_path / "memory.db")
    project = store.create("Synthetic inline browser fixture", "reviewer")["id"]
    store.save(project, "reviewer", "requirements-input", {"document": "Synthetic baseline"}, 0, [])
    records = ProjectWorkItems(store)
    requirement = records.save(
        project, "reviewer", "ba", item("requirement", "Retain human review")
    )
    target = requirement
    review_role = (
        activity if activity in {"product_owner", "developer", "release_manager"} else "admin"
    )
    if activity == "suggestion":
        store.save(
            project,
            "reviewer",
            "requirements",
            {
                "document": "Synthetic agent fixture; not a live result",
                "tasks": [
                    {
                        "id": "fixture-task",
                        "title": "Clarify review criterion",
                        "acceptance_criteria": ["Synthetic supplied review criterion"],
                        "requirement_refs": ["fixture-BRD:1"],
                    }
                ],
            },
            0,
            [{"stage": "requirements-input", "version": 1}],
        )
    elif review_role != "admin":
        story = records.save(
            project,
            "reviewer",
            "product_owner",
            item("story", "Role-owned delivery record", links=[requirement["id"]]),
        )
        target = story
        if activity == "release_manager":
            target = records.save(
                project,
                "reviewer",
                "release_manager",
                item("release", "Release candidate", links=[story["id"]]),
            )
        with store.connect() as db:
            db.execute("INSERT INTO project_members VALUES (?,?)", (project, "ba-user"))
        stage = {
            "product_owner": "backlog_generation",
            "developer": "development",
            "release_manager": "release_readiness",
        }[activity]
        reach(ProjectLifecycle(store), project, stage)
    else:
        target = records.save(
            project,
            "reviewer",
            "test_lead",
            item("test_case", "Validate supplied criterion", links=[requirement["id"]]),
        )
        # Existing lifecycle helper uses ba-user as actor; explicitly invite the fixture identity.
        with store.connect() as db:
            db.execute("INSERT INTO project_members VALUES (?,?)", (project, "ba-user"))
        reach(ProjectLifecycle(store), project, "qa_testing")
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def route(request):
            path = urlparse(request.request.url).path
            method = request.request.method
            prefix = f"/api/sdlc/projects/{project}"
            if path == "/api/auth/profile":
                request.fulfill(
                    json={
                        "username": "reviewer",
                        "display_name": "Fixture reviewer",
                        "is_admin": review_role == "admin",
                        "role": review_role,
                        "capabilities": capabilities(review_role),
                    }
                )
            elif path == "/api/sdlc/projects":
                request.fulfill(json=store.projects("reviewer"))
            elif path == prefix:
                request.fulfill(json=store.snapshot(project, "reviewer"))
            elif path == prefix + "/lifecycle":
                request.fulfill(
                    json=ProjectLifecycle(store).snapshot(project, "reviewer", review_role)
                )
            elif path == prefix + "/work-items" and method == "GET":
                request.fulfill(json=records.list(project, "reviewer"))
            elif path == prefix + "/work-items":
                body = WorkItemInput.model_validate(request.request.post_data_json)
                request.fulfill(
                    status=201,
                    json=records.save(project, "reviewer", review_role, body.model_dump()),
                )
            elif path.endswith("/detail") and path.startswith(prefix):
                identifier = path.split("/")[-2]
                request.fulfill(
                    json=ProjectReviews(store).detail(project, identifier, "reviewer", review_role)
                )
            elif path.endswith("/annotations") and path.startswith(prefix):
                identifier = path.split("/")[-2]
                body = AnnotationInput.model_validate(request.request.post_data_json)
                request.fulfill(
                    status=201,
                    json=ProjectReviews(store).annotate(
                        project, identifier, "reviewer", "admin", body.model_dump()
                    ),
                )
            else:
                mobile_route(request)

        page.route("**/*", route)
        page.add_init_script(
            "localStorage.setItem('sdlc-active-project:reviewer', " + json.dumps(project) + ")"
        )
        page.goto("http://localhost/sdlc")
        if activity == "suggestion":
            page.wait_for_function("() => window.navigateWorkspace !== undefined")
            page.evaluate("window.navigateWorkspace('/sdlc?phase=requirements')")
        page.locator(".record-row", has_text=target["title"]).click()
        form = page.locator("#lifecycle-item-form")
        if activity == "suggestion":
            # Hold the review response to exercise the actual pending-request state.
            held = []
            pattern = f"**/work-items/{target['id']}/detail"
            page.route(pattern, lambda request: held.append(request))
            page.locator(".record-row", has_text=target["title"]).click()
            page.wait_for_function(
                "() => document.querySelector('#record-context').textContent.includes('Loading')"
            )
            pw.expect(form.locator('[name="title"]')).to_be_disabled()
            pw.expect(page.locator("#record-review")).to_be_hidden()
            held[0].fulfill(
                json=ProjectReviews(store).detail(project, target["id"], "reviewer", "admin")
            )
            page.unroute(pattern)
            pw.expect(form.locator('[name="title"]')).to_be_enabled()
            page.locator("#record-ai-panel summary").click()
            page.get_by_role("button", name="Use in draft", exact=True).click()
            pw.expect(form.locator('[name="acceptance_criteria"]')).to_have_value(
                "Synthetic supplied review criterion"
            )
            assert records.list(project, "reviewer")[0]["version"] == 1
            assert records.list(project, "reviewer")[0]["acceptance_criteria"] == []
            original_url = page.url
            page.evaluate("window.navigateWorkspace('/sdlc?phase=backlog')")
            assert page.url == original_url
            page.go_back()
            pw.expect(page).to_have_url(original_url)
            pw.expect(form.locator('[name="acceptance_criteria"]')).to_have_value(
                "Synthetic supplied review criterion"
            )
            form.get_by_role("button", name="Save changes").click()
            page.wait_for_function(
                "() => document.querySelector('#record-context').textContent.includes('v2')"
            )
            saved = records.list(project, "reviewer")[0]
            assert saved["acceptance_criteria"] == ["Synthetic supplied review criterion"]
            assert saved["references"] == ["agent-artifact:requirements:v1:task:fixture-task"]
            page.get_by_role("button", name="Dismiss suggestion", exact=True).click()
            pw.expect(page.locator("#record-comments")).to_contain_text("Suggestion dismissed")
            assert records.list(project, "reviewer")[0]["version"] == 2
        elif review_role != "admin":
            pw.expect(form.locator('[name="references"]')).to_be_enabled()
            if review_role == "developer":
                pw.expect(form.locator('[name="title"]')).to_be_disabled()
                pw.expect(form.locator('[name="acceptance_criteria"]')).to_be_disabled()
            else:
                pw.expect(form.locator('[name="title"]')).to_be_enabled()
            page.locator("#record-options > summary").click()
            form.locator('[name="references"]').fill("fixture-review://human-supplied-reference")
            form.get_by_role("button", name="Save changes").click()
            pw.expect(page.locator("#record-context")).to_contain_text("v2")
            saved = next(
                row for row in records.list(project, "reviewer") if row["id"] == target["id"]
            )
            assert saved["references"] == ["fixture-review://human-supplied-reference"]
            assert saved["title"] == target["title"]
            if review_role == "developer":
                pw.expect(form.locator('[name="title"]')).to_be_disabled()
            page.reload()
            page.locator(".record-row", has_text=target["title"]).click()
            pw.expect(form.locator('[name="references"]')).to_have_value(
                "fixture-review://human-supplied-reference"
            )
            if review_role == "developer":
                page.locator("#record-new").click()
                pw.expect(form.locator('[name="kind"]')).to_have_value("defect")
                assert form.locator('[name="kind"] option[value="story"]').evaluate(
                    "option => option.disabled"
                ), form.locator('[name="kind"]').evaluate("select => select.outerHTML")
            if review_role == "release_manager":
                reach(ProjectLifecycle(store), project, "closed")
                page.reload()
                pw.expect(page.locator("#lifecycle-status")).to_contain_text("Completed")
                pw.expect(page.locator("#lifecycle-status")).not_to_contain_text("Work in progress")
        elif activity == "traceability":
            page.locator("#record-traceability").get_by_role(
                "button", name="Source: requirement"
            ).click()
            pw.expect(page.locator("#sdlc-step-heading")).to_have_text("Requirements")
            pw.expect(page.locator("#record-context")).to_contain_text("Business approved")
            pw.expect(form.locator('[name="title"]')).to_have_value(requirement["title"])
            pw.expect(form.locator('[name="title"]')).to_be_disabled()
            pw.expect(page.locator("#record-create-defect")).to_be_hidden()
            page.get_by_role("button", name="Revise requirement", exact=True).click()
            pw.expect(form.locator('[name="title"]')).to_be_enabled()
        else:
            page.get_by_role("button", name="Create linked defect", exact=True).click()
            form.locator('[name="description"]').fill(
                "Synthetic observed failure from the test fixture"
            )
            form.locator('[name="references"]').fill("fixture-execution://failed-check")
            form.get_by_role("button", name="Save changes").click()
            page.locator(".record-row", has_text="Defect: Validate supplied criterion").wait_for()
            defect = next(
                record for record in records.list(project, "reviewer") if record["kind"] == "defect"
            )
            assert defect["links"] == [target["id"]]
            assert defect["status"] == "draft"
            assert defect["references"] == ["fixture-execution://failed-check"]
        assert not errors
        browser.close()
