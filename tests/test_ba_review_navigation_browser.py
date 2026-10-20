"""BA child links follow current-source assessments on the selected BA workspace."""

import json
import os

import pytest
from test_project_selection_browser import selection_browser as selection_browser

from app.models import GenerateRequest
from app.services.project_lifecycle import ProjectLifecycle
from app.services.requirements_reviews import record_assessment

pytestmark = pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Browser check")


@pytest.mark.parametrize(
    "case", ["no-source", "unreviewed", "review-only", "handoff-only", "ready", "revised"]
)
def test_ba_child_links_require_current_review_on_ba_workspace(selection_browser, case):
    page, store, _ = selection_browser
    project = store.create("BA navigation fixture", "reviewer")["id"]
    source = GenerateRequest(description="Synthetic BRD for quotation requirement review.")
    if case != "no-source":
        store.save(
            project,
            "reviewer",
            "requirements-input",
            {
                "document": source.description,
                "source_request": source.model_dump(mode="json"),
            },
            0,
            [],
        )
    if case in {"review-only", "ready", "revised"}:
        record_assessment(
            store,
            "reviewer",
            source,
            "business_analysis",
            {
                "summary": "Synthetic reviewed BRD for navigation gating.",
                "scope": ["Quotation requirements"],
                "outcome": "ready_for_business_review",
            },
        )
        record_assessment(
            store,
            "reviewer",
            source,
            "alignment",
            {"status": "aligned", "message": "Synthetic alignment"},
        )
    flow = ProjectLifecycle(store)
    if case in {"handoff-only", "ready", "revised"}:
        state = flow.snapshot(project, "reviewer", "admin")
        current = next(item for item in state["definition"] if item["id"] == state["stage"])
        for kind in current["evidence"]:
            flow.evidence(
                project,
                "reviewer",
                "admin",
                {
                    "revision": state["revision"],
                    "kind": kind,
                    "reference": "fixture://review",
                    "outcome": "passed",
                    "comment": "Synthetic human attestation for navigation check",
                },
            )
            state = flow.snapshot(project, "reviewer", "admin")
        flow.transition(
            project,
            "reviewer",
            "admin",
            {
                "revision": state["revision"],
                "decision": "approved",
                "comment": "Synthetic handoff to BA review",
            },
            human=True,
        )
        assert flow.snapshot(project, "reviewer", "admin")["stage"] == "ba_validation"
    if case == "revised":
        revised = source.model_copy(update={"description": "A changed BRD requires a new review."})
        store.save(
            project,
            "reviewer",
            "requirements-input",
            {
                "document": revised.description,
                "source_request": revised.model_dump(mode="json"),
            },
            1,
            [],
        )
    page.add_init_script(
        "sessionStorage.setItem('sdlc-active-project:reviewer', " + json.dumps(project) + ")"
    )
    page.goto("http://localhost/sdlc?phase=business-approval&review=decision")
    page.wait_for_function("document.documentElement.dataset.projectContext === 'ready'")
    page.wait_for_function(
        "document.getElementById('business-approval-context').textContent.includes('Review status')"
    )
    if case in {"ready", "review-only"}:
        assert page.locator("#ba-review-navigation a").count() == 4
        assert (
            page.locator('#ba-review-navigation [aria-current="page"]').inner_text()
            == "Your decision"
        )
        assert page.locator("#ba-feedback-rework").is_visible()
        assert page.locator("#ba-business-delivery").is_hidden()
        page.reload()
        page.locator("#ba-feedback-rework").wait_for()
        assert (
            page.locator('#ba-review-navigation [aria-current="page"]').inner_text()
            == "Your decision"
        )
        page.locator('#ba-review-navigation [data-ba-section="overview"]').click()
        page.locator("#ba-business-delivery").wait_for()
        page.go_back()
        page.locator("#ba-feedback-rework").wait_for()
        page.locator('#ba-signoff-comment').fill("Draft feedback to preserve")
        assert page.locator("#sdlc-view-progress").is_hidden()
        page.locator('#ba-review-navigation [data-ba-section="progress"]').click()
        assert "view=pipeline" in page.url
        assert page.locator("#ba-review-navigation a").count() == 4
        assert (
            page.locator('#ba-review-navigation [aria-current="page"]').inner_text()
            == "View progress"
        )
        page.locator('#ba-review-navigation [data-ba-section="decision"]').click()
        page.locator("#ba-feedback-rework").wait_for()
        assert "review=decision" in page.url
        assert (
            page.locator('#ba-signoff-comment').input_value()
            == "Draft feedback to preserve"
        )
        page.locator('#ba-review-navigation [data-ba-section="progress"]').click()
        page.reload()
        page.locator(
            '#ba-review-navigation [data-ba-section="progress"][aria-current="page"]'
        ).wait_for()
        assert page.locator("#sdlc-view-progress").is_hidden()
        page.locator('#ba-review-navigation [data-ba-section="decision"]').click()
        from playwright.sync_api import expect

        expect(page.locator("#lifecycle-decision")).to_be_hidden()
        expect(page.get_by_role("button", name="Sign off for story drafting", exact=True)).to_be_disabled()
        if case == "ready":
            # Navigation follows the server's effective sign-off, including revocation.
            signed = {"value": True}
            def signed_snapshot(route):
                snapshot = flow.snapshot(project, "reviewer", "admin")
                snapshot["backlog_drafting"]["signed_off"] = signed["value"]
                route.fulfill(json=snapshot)
            pattern = f"**/api/sdlc/projects/{project}/lifecycle"
            page.route(pattern, signed_snapshot)
            page.evaluate("window.dispatchEvent(new Event('requirements-assessment-updated'))")
            expect(page.locator("#ba-review-navigation a")).to_have_count(5)
            page.locator('#ba-review-navigation [data-ba-section="history"]').click()
            expect(page.locator("#ba-business-documents")).to_be_visible()
            page.reload()
            expect(page.locator("#ba-business-documents")).to_be_visible()
            signed["value"] = False
            page.evaluate("window.dispatchEvent(new Event('requirements-assessment-updated'))")
            expect(page.locator("#ba-review-navigation a")).to_have_count(4)
            expect(page.locator("#ba-business-documents")).to_be_hidden()
            expect(page.locator("#ba-feedback-rework")).to_be_visible()
            page.unroute(pattern, signed_snapshot)
        submitted = []
        def request_changes(route):
            payload = route.request.post_data_json
            submitted.append(payload)
            route.fulfill(status=201, json=flow.transition(
                project, "reviewer", "admin", payload, human=True
            ))
        page.route(f"**/api/sdlc/projects/{project}/transitions", request_changes)
        page.locator("#ba-signoff-comment").fill("Clarify the business outcomes before sign-off.")
        page.locator(".ba-signoff").get_by_role("button", name="Request changes", exact=True).click()
        expect(page.locator(".ba-signoff")).to_contain_text("Changes requested.")
        assert len(submitted) == 1
        assert submitted[0]["comment"] == "Clarify the business outcomes before sign-off."
        assert flow.snapshot(project, "reviewer", "admin")["stage"] == (
            "clarification" if case == "ready" else "brd_upload"
        )
    else:
        assert page.locator("#ba-review-navigation").count() == 0
