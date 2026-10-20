"""Requirements offers source import, provider selection, validation and cancellation."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest
from test_mobile_navigation_browser import mobile_route

from app.roles import capabilities
from app.services.project_lifecycle import ProjectLifecycle
from app.services.project_work_items import ProjectWorkItems
from app.services.sdlc import SDLCStore


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize(
    "source", ["upload", "jira", "cancel", "summary-error", "no-evidence", "zero-coverage"]
)
def test_simple_requirements_sources_validation_and_stop(source, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    store = SDLCStore(tmp_path / "memory.db")
    project = store.create("Requirements review", "reviewer")["id"]
    requests, cancellations, errors = [], [], []
    summary_requests = []
    document_requests = []
    pending = []
    text = "The quotation permits a negative deposit."
    report = {
        "status": "blocked",
        "message": "Requirements blocked: resolve the business-alignment findings.",
        "findings": [
            {
                "requirement_id": "REQ-001",
                "status": "conflict",
                "reason": "Negative deposits conflict with the approved rule.",
                "suggested_change": "Reject a negative deposit.",
                "evidence": [],
            }
        ],
        "requirements": {"REQ-001": text},
    }

    def route(request):
        path = urlparse(request.request.url).path
        prefix = f"/api/sdlc/projects/{project}"
        if path == "/api/auth/profile":
            request.fulfill(
                json={
                    "username": "reviewer",
                    "display_name": "Reviewer",
                    "role": "admin",
                    "is_admin": True,
                    "capabilities": capabilities("admin"),
                }
            )
        elif path == "/api/sdlc/projects":
            request.fulfill(json=store.projects("reviewer"))
        elif path == prefix:
            request.fulfill(json=store.snapshot(project, "reviewer"))
        elif path == prefix + "/lifecycle":
            request.fulfill(json=ProjectLifecycle(store).snapshot(project, "reviewer", "admin"))
        elif path == prefix + "/work-items":
            request.fulfill(json=ProjectWorkItems(store).list(project, "reviewer"))
        elif path.startswith(prefix + "/artifacts/") and request.request.method == "POST":
            payload = request.request.post_data_json
            stage = path.split("/")[-1]
            content = payload["content"]
            if stage == "requirements-input":
                content = {**content, "document": content["source_request"]["description"]}
            request.fulfill(
                status=201,
                json=store.save(
                    project, "reviewer", stage, content, payload["base_version"], payload["links"]
                ),
            )
        elif path == "/api/llm/models":
            request.fulfill(
                json={
                    "models": [
                        {
                            "model": "codex",
                            "display_name": "Codex GPT-6-ASTRA",
                            "can_use": True,
                            "reason": "Synthetic fixture",
                        }
                    ]
                }
            )
        elif path == "/api/llm/models/codex/access":
            request.fulfill(
                json={
                    "model": "codex",
                    "display_name": "Codex GPT-6-ASTRA",
                    "can_use": True,
                    "reason": "Synthetic fixture",
                    "policy": "fixed",
                }
            )
        elif path == "/api/workflow/ba-review":
            summary_requests.append(request.request.post_data_json)
            if source == "summary-error":
                request.fulfill(status=503, json={"detail": "Synthetic provider unavailable"})
            else:
                request.fulfill(
                    json={
                        "summary": "The BRD describes vehicle finance quotation deposit checks.",
                        "outcome": "needs_clarification",
                        "objectives": ["Validate quotation deposits"],
                        "scope": ["Quotation validation only"],
                        "areas": [],
                        "findings": [],
                        "open_questions": [],
                        "next_steps": [],
                        "domain_scope": {"product": "PCP", "journeys": ["quotation"]},
                        "domain_validation": {
                            "status": "needs_clarification",
                            "topics_reviewed": 4,
                            "covered": 0 if source == "zero-coverage" else 2,
                            "brd_gaps": 3 if source == "zero-coverage" else 1,
                            "knowledge_gaps": 0,
                            "not_applicable": 1,
                            "alignment_percent": 0 if source == "zero-coverage" else 66.7,
                            "alignment_assessable": 3,
                            "alignment_unassessable": 0,
                            "evidence_verified": source != "no-evidence",
                            "gaps": 3 if source == "zero-coverage" else 1,
                            "conflicts": 0,
                        },
                        "domain_checks": [
                            {
                                "topic_id": "DOMAIN-RULE:deposit",
                                "status": "gap",
                                "reason": "Clarify the supplied deposit constraint.",
                                "recommendation": "Confirm deposit rules with the business owner.",
                                "evidence": [],
                            },
                            {
                                "topic_id": "DOMAIN:product",
                                "status": "gap" if source == "zero-coverage" else "covered",
                                "reason": "The BRD identifies the relevant finance product.",
                                "evidence": [
                                    {
                                        "source_id": "GUIDE:product",
                                        "quote": "Synthetic product reference",
                                    }
                                ],
                            },
                            {
                                "topic_id": "DOMAIN:journey",
                                "status": "gap" if source == "zero-coverage" else "covered",
                                "reason": "The BRD identifies the quotation journey.",
                                "evidence": [],
                            },
                            {
                                "topic_id": "DOMAIN:servicing",
                                "status": "not_applicable",
                                "reason": "Servicing is outside the supplied scope.",
                                "evidence": [],
                            },
                        ],
                        "knowledge_sources": [
                            {
                                "title": "Auto-finance guide",
                                "version": "fixture",
                                "authority": "reference_only",
                            }
                        ],
                        "knowledge_limitations": [],
                    }
                )
        elif path == "/api/workflow/requirements/document":
            document_requests.append(path)
            request.fulfill(
                json={
                    "description": text,
                    "filename": "Requirements.pdf",
                    "uploaded_brd_receipt": "synthetic-receipt",
                }
            )
        elif path == "/api/jira/issues/QA-123/requirements":
            request.fulfill(
                json={
                    "issue_key": "QA-123",
                    "summary": "Deposit validation",
                    "description": text,
                    "acceptance_criteria": ["Validate deposits"],
                }
            )
        elif path == "/api/workflow/validate-requirements":
            requests.append(request.request.post_data_json)
            if source == "cancel":
                pending.append(request)
            else:
                request.fulfill(
                    status=422,
                    json={
                        "detail": {"message": report["message"], "requirements_validation": report}
                    },
                )
        elif path.endswith("/cancel"):
            cancellations.append(path)
            request.fulfill(json={"cancelled": True})
        else:
            mobile_route(request)

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.add_init_script(
            "sessionStorage.setItem('sdlc-active-project:reviewer', " + json.dumps(project) + ")"
        )
        page.goto("http://localhost/")
        pw.expect(page.locator("#llm-model")).to_have_value("codex")
        activity = page.locator(".requirements-agent-activity")
        pw.expect(activity).to_contain_text("Summarise the BRD")
        pw.expect(activity).to_contain_text("Validate source alignment")
        pw.expect(activity).to_contain_text("Your action")
        pw.expect(activity).not_to_contain_text("Generate stories")
        pw.expect(page.locator("#stop-generation")).to_be_visible()
        pw.expect(page.locator("#stop-generation")).to_be_disabled()
        pw.expect(page.locator("#validate-requirements")).to_be_disabled()
        assert page.locator("#requirements-next-stage").count() == 0
        for selector in [
            "#ba-review",
            "#generate",
            ".ba-approved-check",
            ".sdlc-source-baseline",
            ".sdlc-stage-checklist",
            "#sdlc-step-links",
        ]:
            pw.expect(page.locator(selector).first).to_be_hidden()
        pw.expect(page.locator("#requirements-options")).to_be_hidden()
        assert page.locator("#requirements-options").get_attribute("open") is None
        if source == "upload":
            input_size = page.locator("#description").bounding_box()
            page.locator("#add-requirement-source").click()
            page.locator("#requirement-file").set_input_files(
                {"name": "Requirements.pdf", "mimeType": "application/pdf", "buffer": b"fixture"}
            )
            pw.expect(page.locator("#file-name")).to_have_text("Requirements.pdf")
            pw.expect(page.locator("#description")).to_be_visible()
            pw.expect(page.locator("#description")).to_have_attribute("readonly", "")
            pw.expect(page.locator("#description")).to_have_value("")
            page.locator("#description").press("x")
            pw.expect(page.locator("#description")).to_have_value("")
            attached_size = page.locator("#description").bounding_box()
            assert abs(attached_size["width"] - input_size["width"]) <= 1
            assert abs(attached_size["height"] - input_size["height"]) <= 1
            pw.expect(page.locator("#add-requirement-source")).to_be_hidden()
            pw.expect(page.locator("#source-state")).to_be_hidden()
        elif source == "jira":
            page.locator("#add-requirement-source").click()
            page.locator("#show-jira-link").click()
            page.locator("#load-jira").click()
            pw.expect(page.locator("#jira-source-key")).to_have_attribute("aria-invalid", "true")
            page.locator("#jira-source-key").fill("https://example.atlassian.net/browse/QA-123")
            page.locator("#load-jira").click()
            pw.expect(page.locator("#description")).to_have_value(re.compile("Jira story QA-123"))
        else:
            page.locator("#description").fill(text)
        page.locator("#llm-model").select_option("codex")
        pw.expect(page.locator("#llm-model")).to_have_attribute("data-access", "allowed")
        page.locator("#close-model-access").click()
        pw.expect(page.locator("#requirements-validation-report")).to_be_hidden()
        assert not summary_requests
        assert not document_requests
        assert not requests
        with page.expect_request("**/api/workflow/validate-requirements"):
            page.locator("#validate-requirements").click()
        if source == "cancel":
            pw.expect(page.locator("#generation-overlay-title")).to_contain_text(
                "Validating requirements"
            )
            popup = page.locator("#generation-overlay")
            pw.expect(popup.locator("#operation-state")).to_have_text("In progress")
            pw.expect(popup.locator("#operation-source")).to_have_text("Current requirements")
            pw.expect(popup.locator("#operation-output")).to_contain_text("BA review")
            pw.expect(popup.locator("#operation-review-focus li")).to_have_count(3)
            page.evaluate("""() => renderLifecycleEvents([{
                sequence: 1, agent: 'Requirements Validation Agent', status: 'running',
                action: 'validation_started',
                summary: 'Comparing the supplied requirements with approved business sources.'
            }])""")
            pw.expect(popup.locator("#generation-current-activity")).to_contain_text(
                "Comparing the supplied requirements"
            )
            for width in [1440, 390]:
                page.set_viewport_size({"width": width, "height": 900})
                assert popup.locator(".generation-dialog").evaluate(
                    "element => element.getBoundingClientRect().right <= innerWidth"
                )
                assert popup.locator(".generation-dialog-footer").evaluate(
                    "element => element.getBoundingClientRect().bottom <= innerHeight"
                )
                page.screenshot(path=f"/tmp/workflow-activity-{width}.png", animations="disabled")
            page.locator("#cancel-generation-overlay").focus()
            page.keyboard.press("Tab")
            assert page.evaluate(
                "document.getElementById('generation-overlay').contains(document.activeElement)"
            )
            page.keyboard.press("Shift+Tab")
            pw.expect(page.locator("#cancel-generation-overlay")).to_be_focused()
            page.emulate_media(reduced_motion="reduce")
            assert (
                popup.locator(".generation-dialog").evaluate(
                    "element => getComputedStyle(element).animationName"
                )
                == "none"
            )
            page.locator("#background-generation-overlay").click()
            page.locator("#reopen-generation").click()
            pw.expect(popup).to_be_visible()
            page.keyboard.press("Escape")
            pw.expect(popup).to_be_hidden()
            page.locator("#stop-generation").click()
            pw.expect(page.locator("#status")).to_contain_text("cancelled")
            assert cancellations
        else:
            panel = page.locator("#requirements-validation-report")
            pw.expect(panel).to_contain_text("Negative deposits conflict with the approved rule.")
            assert panel.evaluate("element => element.previousElementSibling.id") == "test-studio"
            assert (
                panel.bounding_box()["y"]
                >= page.locator("#test-studio").bounding_box()["y"]
                + page.locator("#test-studio").bounding_box()["height"]
            )
            assert "Suggested fix" not in panel.inner_text()
            assert page.locator("#preview-brd-draft, #download-brd-draft").count() == 0
            if source == "upload":
                assert requests[0]["uploaded_brd_receipt"] == "synthetic-receipt"
        assert requests[0]["llm_model"] == "codex"
        score = page.locator("#brd-domain-coverage")
        pw.expect(page.locator(".brd-metrics")).to_contain_text("Domain topic coverage")
        assert "BRD-to-domain confidence" not in page.locator(".brd-metrics").inner_text()
        if source in ["summary-error", "no-evidence"]:
            pw.expect(score).to_have_text("Not assessable")
            assert page.locator(".brd-confidence meter").count() == 0
        elif source == "zero-coverage":
            pw.expect(score).to_have_text("0 of 3 topics fully covered")
            pw.expect(page.locator(".brd-metrics")).to_contain_text(
                "No assessed topic is fully covered yet"
            )
            pw.expect(page.locator(".brd-coverage-reasons")).to_contain_text(
                "Confirm deposit rules with the business owner."
            )
        else:
            pw.expect(score).to_have_text("2 of 3 topics fully covered")
            pw.expect(page.locator(".brd-confidence meter")).to_have_attribute("value", "66.7")
        assert page.locator(".brd-sample-metrics").count() == 0
        assert len(summary_requests) == 1
        assert summary_requests[0]["llm_model"] == "codex"
        summary_panel = page.locator("#requirements-validation-report")
        if source == "summary-error":
            pw.expect(summary_panel).to_contain_text("BRD summary and domain review unavailable")
            assert summary_panel.get_attribute("data-status") == "incomplete"
        else:
            pw.expect(summary_panel).to_contain_text("Validation result & summary")
            pw.expect(summary_panel).to_contain_text("Quotation validation only")
            pw.expect(summary_panel).to_contain_text("Auto-finance domain review")
            pw.expect(summary_panel).to_contain_text("Clarify the supplied deposit constraint.")
            summary_panel.locator("summary").click()
            pw.expect(summary_panel).to_contain_text("reference only")
            assert summary_requests[0]["description"] == requests[0]["description"]
        pw.expect(page.locator("#stop-generation")).to_be_disabled()
        with page.expect_download() as download_info:
            page.locator("#download-brd-report").click()
        download = download_info.value
        assert download.suggested_filename == "BRD-validation-and-domain-review.html"
        html = Path(download.path()).read_text()
        assert "All auto-finance domain checks" in html
        assert "Complete assessment data and source traceability" in html
        assert "illustrative only" not in html
        if source != "summary-error":
            assert "Auto-finance guide" in html
            assert "DOMAIN-RULE:deposit" in html
            if source not in ["no-evidence", "zero-coverage"]:
                assert "66.7%" in html
            assert "DOMAIN:servicing" in html
        else:
            assert "Synthetic provider unavailable" in html
        page.screenshot(
            path=f"/tmp/brd-summary-{source}.png", full_page=True, animations="disabled"
        )
        for theme in ["light", "dark"]:
            page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
            for width in [390, 768, 1440]:
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                trigger = page.locator("#add-requirement-source")
                if source == "upload":
                    pw.expect(trigger).to_be_hidden()
                else:
                    pw.expect(trigger).to_be_visible()
                pw.expect(page.locator("#llm-model")).to_be_visible()
                boxes = page.evaluate("""() => Object.fromEntries(
                    ['description', 'add-requirement-source', 'llm-model',
                     'validate-requirements', 'stop-generation'].map(id => [id,
                        document.getElementById(id).getBoundingClientRect().toJSON()]))""")
                input_box = (
                    page.locator(".textarea-wrap").first.bounding_box()
                    if source == "upload"
                    else boxes["description"]
                )
                plus_box = boxes["add-requirement-source"]
                assert input_box and plus_box
                if source != "upload":
                    assert plus_box["y"] >= input_box["y"]
                    assert plus_box["y"] + plus_box["height"] <= (
                        input_box["y"] + input_box["height"]
                    )
                model = boxes["llm-model"]
                validate = boxes["validate-requirements"]
                stop = boxes["stop-generation"]
                assert model and validate and stop
                assert abs(validate["y"] - stop["y"]) <= 1
                if width == 1440:
                    assert abs(model["y"] - validate["y"]) <= 1
                if source != "upload":
                    trigger.click()
                    pw.expect(page.locator("#upload-zone")).to_be_visible()
                    pw.expect(page.locator("#show-jira-link")).to_be_visible()
                    page.keyboard.press("Escape")
                pw.expect(page.locator("#requirement-source-menu")).to_be_hidden()
                if source != "upload":
                    pw.expect(trigger).to_be_focused()
        if source == "cancel":
            assert page.locator("#requirements-next-stage").count() == 0
        else:
            if source == "upload":
                page.reload()
                pw.expect(page.locator("#requirements-validation-report")).to_be_visible()
            next_stage = page.locator("#requirements-next-stage")
            pw.expect(next_stage).to_have_text("Next stage: BA review & approval →")
            pw.expect(next_stage).to_be_enabled()
            if source == "upload":
                page.evaluate("""() => {
                    const persist = window.persistReviewedRequirements;
                    let failOnce = true;
                    window.persistReviewedRequirements = async () => {
                        if (failOnce) {
                            failOnce = false;
                            throw new Error('Save unavailable. Retry the handoff.');
                        }
                        return persist();
                    };
                }""")
                next_stage.click()
                pw.expect(page.locator("#requirements-handoff-status")).to_have_text(
                    "Save unavailable. Retry the handoff."
                )
                pw.expect(next_stage).to_be_enabled()
            next_stage.click()
            pw.expect(page.locator("h1")).to_have_text("BA review & approval")
            assert len(requests) == 1
            assert len(summary_requests) == 1
            page.locator("#sdlc-phase-requirements").click()
            pw.expect(page.locator("h1")).to_have_text("Requirements")
            pw.expect(page.locator("#requirements-validation-report")).to_be_visible()
            if source == "upload":
                pw.expect(page.locator("#description")).to_be_visible()
                pw.expect(page.locator("#description")).to_have_attribute("readonly", "")
                pw.expect(page.locator("#description")).to_have_value("")
                page.locator("#file-remove").click()
                pw.expect(page.locator("#requirements-validation-report")).to_be_hidden()
                draft = page.evaluate(
                    "JSON.parse(sessionStorage.getItem('quality-workspace-draft:v1:reviewer'))"
                )
                assert draft["sourceAttachment"] is None
                assert draft["savedRequirementsReport"] is None
                assert draft["savedBaReport"] is None
                assert draft["state"]["request"] is None
                pw.expect(page.locator("#add-requirement-source")).to_be_visible()
                pw.expect(page.locator("#description")).to_be_visible()
                assert not page.locator("#description").evaluate("element => element.readOnly")
                pw.expect(page.locator("#description")).to_have_value("")
            page.locator("#description").fill("Changed requirements must be validated again.")
            pw.expect(page.locator("#requirements-validation-report")).to_be_hidden()
        assert not errors
        browser.close()
