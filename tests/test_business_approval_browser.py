"""Business approval uses real local stores with explicitly synthetic assessment evidence."""

import json
import os
from urllib.parse import urlparse

import pytest
from test_mobile_navigation_browser import mobile_route
from test_project_lifecycle import reach

from app.models import GenerateRequest
from app.roles import capabilities
from app.sdlc_routes import TransitionInput, WorkItemInput
from app.services.project_lifecycle import ProjectLifecycle
from app.services.project_work_items import ProjectWorkItems
from app.services.requirements_reviews import record_assessment
from app.services.sdlc import SDLCError, SDLCStore


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("blocked,width", [(False, 1440), (True, 390)])
def test_approval_reviews_exact_brd_and_retains_human_decision(tmp_path, blocked, width):
    pw = pytest.importorskip("playwright.sync_api")
    store = SDLCStore(tmp_path / "memory.db")
    project = store.create("Business approval fixture", "ba-user")["id"]
    source = GenerateRequest(
        description="Synthetic BRD: quotation deposits require business review."
    )
    store.save(
        project,
        "ba-user",
        "requirements-input",
        {"document": source.description, "source_request": source.model_dump(mode="json")},
        0,
        [],
    )
    record_assessment(
        store,
        "ba-user",
        source,
        "business_analysis",
        {
            "summary": "Synthetic source-grounded quotation BRD assessment.",
            "outcome": "needs_clarification" if blocked else "ready_for_business_review",
            "assessed_at": "2026-10-17T12:00:00Z",
            "objectives": ["Review deposit behaviour"],
            "scope": ["Quotation deposit validation"],
            "business_deliverables": [
                {
                    "expectation": "Confirm quotation deposit behaviour with the business",
                    "deliverable": "Reviewed quotation deposit rules",
                    "business_benefit": "Clearer deposit decisions for the delivery team",
                    "delivery_impact": "Agree deposit rules before quotation implementation",
                    "benefit_basis": "inferred_requires_confirmation",
                    "success_measure": None,
                    "document_quote": source.description,
                }
            ],
            "domain_validation": {
                "status": "needs_clarification" if blocked else "covered",
                "topics_reviewed": 1,
                "gaps": int(blocked),
                "conflicts": 0,
            },
        },
    )
    record_assessment(
        store,
        "ba-user",
        source,
        "alignment",
        {
            "status": "blocked" if blocked else "aligned",
            "message": "Synthetic blocked review" if blocked else "Synthetic alignment complete",
        },
    )
    records = ProjectWorkItems(store)
    record = records.save(
        project,
        "ba-user",
        "ba",
        WorkItemInput(
            base_version=0, kind="requirement", title="Review supplied deposit requirement"
        ).model_dump(),
    )
    flow = ProjectLifecycle(store)
    reach(flow, project, "stakeholder_approval")
    errors = []

    def route(request):
        path = urlparse(request.request.url).path
        method = request.request.method
        prefix = f"/api/sdlc/projects/{project}"
        try:
            if path == "/api/auth/profile":
                request.fulfill(
                    json={
                        "username": "ba-user",
                        "display_name": "Fixture stakeholder",
                        "role": "business_stakeholder",
                        "is_admin": False,
                        "capabilities": capabilities("business_stakeholder"),
                    }
                )
            elif path == "/api/sdlc/projects":
                request.fulfill(json=store.projects("ba-user"))
            elif path == prefix:
                request.fulfill(json=store.snapshot(project, "ba-user"))
            elif path == prefix + "/lifecycle":
                request.fulfill(json=flow.snapshot(project, "ba-user", "business_stakeholder"))
            elif path == prefix + "/work-items":
                request.fulfill(json=records.list(project, "ba-user"))
            elif path == prefix + "/transitions" and method == "POST":
                payload = TransitionInput.model_validate(request.request.post_data_json)
                request.fulfill(
                    status=201,
                    json=flow.transition(
                        project, "ba-user", "business_stakeholder", payload.model_dump(), human=True
                    ),
                )
            else:
                mobile_route(request)
        except PermissionError as error:
            request.fulfill(status=403, json={"detail": str(error)})
        except SDLCError as error:
            request.fulfill(status=409, json={"detail": str(error)})

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.add_init_script(
            "sessionStorage.setItem('sdlc-active-project:ba-user', " + json.dumps(project) + ")"
        )
        page.goto("http://localhost/sdlc?phase=business-approval")
        view = page.locator("#business-approval-context")
        pw.expect(view).to_contain_text("BRD baseline · version 1")
        assert (
            page.get_by_role("link", name="Review requirements and BA handoff", exact=True).count()
            == 0
        )
        pw.expect(view).to_contain_text("Synthetic source-grounded quotation BRD assessment.")
        pw.expect(page.locator("#project-lifecycle")).to_be_hidden()
        pw.expect(page.locator(".sdlc-artifact-ledger")).to_be_hidden()
        pw.expect(view.locator('a[href$="ba-documents?document=brd"]').first).to_have_attribute(
            "download", ""
        )
        delivery = page.locator("#ba-business-delivery")
        impact = page.locator("#ba-business-impact")
        suggestions = page.locator("#ba-domain-suggestions")
        feedback = page.locator("#ba-feedback-rework")
        pw.expect(delivery).to_contain_text("Quotation deposit validation")
        pw.expect(delivery).to_contain_text("Reviewed quotation deposit rules")
        pw.expect(impact).to_contain_text("Clearer deposit decisions for the delivery team")
        pw.expect(impact).to_contain_text("Inferred benefit · BA confirmation required")
        pw.expect(impact).to_contain_text("Not specified in the BRD")
        pw.expect(impact.locator("blockquote")).to_have_text(source.description)
        pw.expect(page.locator("#ba-review-navigation a")).to_have_count(4)
        pw.expect(suggestions).to_be_hidden()
        pw.expect(feedback).to_be_hidden()
        page.get_by_role("link", name="Next: AI suggestions", exact=True).click()
        pw.expect(suggestions).to_be_visible()
        pw.expect(delivery).to_be_hidden()
        pw.expect(suggestions.locator("#ba-inline-workspace")).to_have_count(1)
        pw.expect(
            suggestions.get_by_role("heading", name="AI suggestions and BA feedback", exact=True)
        ).to_have_count(1)
        assert "Review the existing BRD · BA view" not in view.inner_text()
        pw.expect(suggestions.locator(".ba-requirements-assessment")).not_to_have_attribute(
            "open", ""
        )
        pw.expect(suggestions.get_by_role("button", name="Generate AI suggestions")).to_be_visible()
        pw.expect(suggestions.locator("#ba-agent-validate")).to_be_disabled()
        page.get_by_role("link", name="Next: Your decision", exact=True).click()
        pw.expect(feedback.locator("#lifecycle-decision")).to_be_visible()
        pw.expect(feedback.get_by_text("Your feedback", exact=True)).to_be_visible()
        pw.expect(feedback.get_by_role("button", name="Approve BRD", exact=True)).to_be_visible()
        pw.expect(
            feedback.get_by_role("button", name="Request changes", exact=True)
        ).to_be_visible()
        pw.expect(page.locator("#project-lifecycle")).to_be_hidden()
        pw.expect(page.locator("#lifecycle-evidence")).to_be_hidden()
        page.screenshot(path=f"/tmp/simple-ba-decision-{width}.png", full_page=True)
        assert page.evaluate("""() => {
            const ids = ['ba-business-delivery', 'ba-business-impact',
                'ba-domain-suggestions', 'ba-feedback-rework'];
            return ids.slice(1).every((id, i) => Boolean(document.getElementById(ids[i])
                .compareDocumentPosition(document.getElementById(id))
                & Node.DOCUMENT_POSITION_FOLLOWING));
        }""")
        pw.expect(page.locator("#ba-agent-validate")).to_be_disabled()
        approve = page.locator('#lifecycle-decision [value="approved"]')
        if blocked:
            pw.expect(approve).to_be_disabled()
            pw.expect(view).to_contain_text("clarification findings")
        else:
            pw.expect(approve).to_be_enabled()
        page.locator('#lifecycle-decision [name="comment"]').fill(
            "Reviewed exact BRD v1 and its source findings."
        )
        page.locator(
            '#lifecycle-decision [value="changes_requested"]'
            if blocked
            else '#lifecycle-decision [value="approved"]'
        ).click()
        target = "clarification" if blocked else "backlog_generation"
        page.wait_for_function(
            "stage => document.querySelector('#lifecycle-status').textContent"
            ".toLowerCase().includes(stage)",
            arg=target.replace("_", " "),
        )
        page.evaluate(
            "window.navigateWorkspace('/sdlc?phase=business-approval&review=history', false)"
        )
        page.reload()
        pw.expect(page.locator("#ba-business-documents")).to_be_hidden()
        pw.expect(
            view.get_by_role("link", name="Download review history", exact=True)
        ).to_be_hidden()
        pw.expect(page.locator("#project-lifecycle")).to_be_hidden()
        pw.expect(page.locator("#lifecycle-decision")).to_be_hidden()
        pw.expect(page.locator("#lifecycle-evidence")).to_be_hidden()
        snapshot = flow.snapshot(project, "ba-user", "business_stakeholder")
        assert snapshot["stage"] == target
        assert (
            snapshot["approval_context"]["decisions"][-1]["work_item_versions"][record["id"]] == 1
        )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=f"/tmp/business-approval-{width}.png", full_page=True)
        assert not errors
        browser.close()
