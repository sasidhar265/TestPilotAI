"""Explicit validation-to-approval handoff persists source and server assessment provenance."""

import json
import os
from urllib.parse import urlparse

import pytest
from test_business_analyst import assessment
from test_mobile_navigation_browser import mobile_route

from app.models import GenerateRequest
from app.roles import capabilities
from app.services.project_lifecycle import ProjectLifecycle
from app.services.project_work_items import ProjectWorkItems
from app.services.requirements_reviews import record_assessment
from app.services.sdlc import SDLCStore


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("provider_unavailable", [False, True])
def test_reviewed_source_is_saved_before_next_stage_and_survives_reload(
    tmp_path, provider_unavailable
):
    pw = pytest.importorskip("playwright.sync_api")
    store = SDLCStore(tmp_path / "memory.db")
    project = store.create("Requirements handoff fixture", "ba-user")["id"]
    flow = ProjectLifecycle(store)
    ba = assessment().model_dump() | {
        "assessed_at": "2026-10-17T12:00:00Z",
        "document_fingerprint": "a" * 64,
        "knowledge_fingerprint": "b" * 64,
        "knowledge_sources": [],
        "knowledge_limitations": [],
        "business_approval": "not_granted",
        "regulatory_compliance": "not_assessed",
        "domain_scope": {},
        "domain_validation": {
            "status": "covered",
            "topics_reviewed": 3,
            "covered": 3,
            "gaps": 0,
            "conflicts": 0,
            "not_applicable": 0,
            "evidence_verified": True,
            "alignment_percent": 100,
            "alignment_assessable": 3,
        },
    }
    alignment = {
        "status": "aligned",
        "message": "Synthetic source alignment complete.",
        "findings": [],
        "sources": [],
        "requirements": {},
        "assessed_at": "2026-10-17T12:00:00Z",
    }
    errors = []
    agent_requests = []
    fail_review = False

    def route(request):
        path = urlparse(request.request.url).path
        method = request.request.method
        prefix = f"/api/sdlc/projects/{project}"
        if path == "/api/auth/profile":
            request.fulfill(
                json={
                    "username": "ba-user",
                    "display_name": "Fixture BA",
                    "role": "admin",
                    "is_admin": True,
                    "capabilities": capabilities("admin"),
                }
            )
        elif path == "/api/llm/models":
            request.fulfill(
                json={
                    "models": [
                        {
                            "model": "codex",
                            "display_name": "GPT-6-ASTRA",
                            "can_use": True,
                            "reason": "Synthetic fixture",
                        }
                    ]
                }
            )
        elif path == "/api/sdlc/projects":
            request.fulfill(json=store.projects("ba-user"))
        elif path == prefix:
            request.fulfill(json=store.snapshot(project, "ba-user"))
        elif path == prefix + "/lifecycle":
            request.fulfill(json=flow.snapshot(project, "ba-user", "admin"))
        elif path == prefix + "/work-items":
            request.fulfill(json=ProjectWorkItems(store).list(project, "ba-user"))
        elif path.startswith(prefix + "/artifacts/") and method == "POST":
            stage = path.split("/")[-1]
            data = request.request.post_data_json
            content = data["content"]
            if stage == "requirements-input":
                source = GenerateRequest.model_validate(content["source_request"])
                content = {
                    "document": source.description,
                    "source_request": source.model_dump(mode="json"),
                }
            saved = store.save(
                project, "ba-user", stage, content, data["base_version"], data["links"]
            )
            request.fulfill(status=201, json=saved)
        elif path in {"/api/workflow/ba-review", "/api/workflow/validate-requirements"}:
            agent_requests.append(path)
            if fail_review:
                request.fulfill(
                    status=503,
                    json={"detail": "BA review unavailable. Check provider access and retry."},
                )
                return
            source = GenerateRequest.model_validate(request.request.post_data_json)
            kind, report = (
                ("business_analysis", ba)
                if path.endswith("ba-review")
                else ("alignment", alignment)
            )
            record_assessment(store, "ba-user", source, kind, report)
            request.fulfill(json=report)
        else:
            mobile_route(request)

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.add_init_script(
            "sessionStorage.setItem('sdlc-active-project:ba-user', " + json.dumps(project) + ")"
        )
        page.goto("http://localhost/")
        pw.expect(page.locator("#llm-model")).to_have_value("codex")
        assert page.locator("#sdlc-save-requirements, #sdlc-start-delivery").count() == 0
        page.locator("#description").fill("Quotation requests must reject a negative deposit.")
        page.locator("#validate-requirements").click()
        pw.expect(page.locator("#requirements-next-stage")).to_be_enabled()
        page.locator("#requirements-next-stage").click()
        pw.expect(page.locator("h1")).to_have_text("BA review & approval")
        pw.expect(page.locator("#ba-review-navigation a")).to_have_count(4)
        page.locator('#ba-review-navigation [data-ba-section="progress"]').click()
        pw.expect(
            page.locator('#ba-review-navigation [data-ba-section="progress"]')
        ).to_have_attribute("aria-current", "page")
        page.locator('#ba-review-navigation [data-ba-section="overview"]').click()
        view = page.locator("#business-approval-context")
        pw.expect(view).to_contain_text("BRD baseline · version 1")
        pw.expect(view).to_contain_text(ba["summary"])
        state = flow.snapshot(project, "ba-user", "admin")
        assert state["stage"] == "requirements_analysis"
        assert set(state["approval_context"]["assessments"]) == {"business_analysis", "alignment"}
        assert not state["approval_context"]["decisions"]
        page.reload()
        pw.expect(view).to_contain_text(ba["summary"])
        before = len(agent_requests)
        assert before == 2  # Initial explicit Requirements validation only.
        fail_review = provider_unavailable
        page.locator('#ba-review-navigation [data-ba-section="suggestions"]').click()
        page.locator(".ba-requirements-assessment > summary").click()
        pw.expect(page.locator("#ba-agent-validate")).to_be_disabled()
        assert len(agent_requests) == before
        # Running, failed, empty, stale and other-project reviews cannot unlock revalidation.
        for review in [
            {"project": project, "baseline": 1, "status": "running", "output": {"findings": [{}]}},
            {"project": project, "baseline": 1, "status": "failed", "output": {"findings": [{}]}},
            {"project": project, "baseline": 1, "status": "completed", "output": {"findings": []}},
            {"project": project, "baseline": 0, "status": "completed", "output": {"findings": [{}]}},
            {"project": "another-project", "baseline": 1, "status": "completed", "output": {"findings": [{}]}},
        ]:
            page.evaluate("""(review) => {
              window.inlineBAReviewSnapshot = () => review;
              window.dispatchEvent(new Event('ba-review-updated'));
            }""", review)
            pw.expect(page.locator("#ba-agent-validate")).to_be_disabled()
        # Exercise the feedback-loop gate independently of provider output.
        page.evaluate("""(project) => {
          window.inlineBAReviewSnapshot = () => ({project, baseline: 1, status: 'completed',
            output: {summary: 'Synthetic feedback-loop suggestions', findings: [{title: 'Clarify deposit rule'}]}});
          window.dispatchEvent(new Event('ba-review-updated'));
        }""", project)
        page.locator(".ba-requirements-assessment > summary").click()
        pw.expect(page.locator("#ba-agent-validate")).to_be_enabled()
        page.locator("#ba-agent-validate").click()
        if provider_unavailable:
            pw.expect(view).to_contain_text(
                "BA review unavailable. Check provider access and retry."
            )
            assert len(agent_requests) == before + 1
        else:
            pw.expect(view).to_contain_text("BA validation saved.")
            assert len(agent_requests) == before + 2
            pw.expect(view).to_contain_text("Clarifications to resolve")
        pw.expect(page.locator("#ba-agent-validate")).to_be_enabled()
        after = flow.snapshot(project, "ba-user", "admin")
        assert after["stage"] == state["stage"]
        assert not after["approval_context"]["decisions"]
        if not provider_unavailable:
            assert after["revision"] > state["revision"]
        page.reload()
        pw.expect(view).to_contain_text(ba["summary"])
        assert len(agent_requests) == before + (1 if provider_unavailable else 2)
        page.locator("#sdlc-phase-requirements").click()
        pw.expect(page.locator("#project-lifecycle")).to_be_hidden()
        pw.expect(page.locator("#lifecycle-decision")).to_be_hidden()
        page.locator("#sdlc-phase-business-approval").click()
        pw.expect(view).to_contain_text(ba["summary"])
        page.locator('#ba-review-navigation [data-ba-section="decision"]').click()
        pw.expect(page.locator("#lifecycle-decision")).to_be_hidden()
        pw.expect(page.locator("#ba-signoff-comment")).to_be_visible()
        assert not errors
        browser.close()
