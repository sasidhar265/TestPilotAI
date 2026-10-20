"""BA analysis progress presents server state without invented completion percentages."""

import json
import os

import pytest
from playwright.sync_api import expect
from test_project_selection_browser import selection_browser as selection_browser

from app.models import GenerateRequest
from app.services.requirements_reviews import record_assessment

pytestmark = pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Browser check")


@pytest.mark.parametrize(
    "status,label",
    [
        (None, "Not started"),
        ("queued", "Queued"),
        ("running", "Analysing BRD"),
        ("completed", "Ready for BA review"),
        ("failed", "Analysis failed"),
        ("cancelled", "Analysis stopped"),
        ("stale", "Not started"),
        ("unavailable", "Status unavailable"),
    ],
)
def test_analysis_status_and_polling_across_ba_sections(selection_browser, status, label):
    page, store, _ = selection_browser
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    project = store.create("Synthetic analysis progress", "reviewer")["id"]
    source = GenerateRequest(description="Quotation expiry must be displayed.")
    store.save(
        project,
        "reviewer",
        "requirements-input",
        {"document": source.description, "source_request": source.model_dump(mode="json")},
        0,
        [],
    )
    for kind in ("business_analysis", "alignment"):
        record_assessment(
            store, "reviewer", source, kind, {"summary": "Synthetic initial assessment"}
        )
    output = {
        "summary": "Synthetic completed analysis",
        "readiness_status": "READY_FOR_BA_REVIEW",
        "requirements": [],
        "findings": [],
        "dependencies": [],
        "calculations": [],
        "business_questions": [],
        "analysis_limitations": [],
        "scope": [],
    }
    review = {
        "id": "synthetic-review",
        "project": project,
        "baseline": 1,
        "revision": 1,
        "status": status,
        "progress": "Synthetic server-reported progress",
        "updated_at": "2026-10-20T12:30:00Z",
        "provider": "codex",
        "sections": [],
        "knowledge_sources": [],
        "output": None,
    }
    if status == "completed":
        review["output"] = output
    if status == "stale":
        review.update(status="completed", baseline=0, output=output)
    response = {"unavailable": status == "unavailable", "run": review if status else None}

    def review_route(route):
        if response["unavailable"]:
            route.fulfill(status=503, json={"detail": "Synthetic status service unavailable"})
        else:
            route.fulfill(json={"run": response["run"], "history": []})

    page.route(f"**/api/sdlc/projects/{project}/ba-reviews", review_route)
    page.add_init_script(
        "sessionStorage.setItem('sdlc-active-project:reviewer', " + json.dumps(project) + ")"
    )
    page.goto("http://localhost/sdlc?phase=business-approval&review=overview")
    panel = page.locator("#ba-analysis-progress")
    expect(panel).to_be_visible()
    expect(panel.locator(".ba-analysis-state")).to_have_text(label)
    if status in {"queued", "running"}:
        expect(panel.get_by_role("progressbar")).to_be_visible()
        assert panel.get_by_role("progressbar").get_attribute("aria-valuenow") is None
        expect(panel).to_contain_text("Synthetic server-reported progress")
        page.locator('#ba-review-navigation [data-ba-section="decision"]').click()
        expect(panel).to_be_visible()
        response["run"] = review | {"status": "completed", "output": output}
        expect(panel.locator(".ba-analysis-state")).to_have_text(
            "Ready for BA review", timeout=10000
        )
        expect(panel.get_by_role("progressbar")).to_have_count(0)
        expect(panel.get_by_role("link", name="Review AI findings")).to_be_visible()
    elif status == "unavailable":
        expect(panel).to_contain_text("Synthetic status service unavailable")
        response.update(unavailable=False, run=None)
        panel.get_by_role("button", name="Retry status check").click()
        expect(panel.locator(".ba-analysis-state")).to_have_text("Not started")
    elif status in {"failed", "cancelled"}:
        expect(panel).to_contain_text("Synthetic server-reported progress")
        expect(panel.get_by_role("link", name="Open AI suggestions")).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 850})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    assert not errors
