"""Isolated real HTTP/SQLite acceptance environment. Only the model response is synthetic.

Run from the repository root with PYTHONPATH=. .venv/bin/python ...
Never use this provider substitution in the application or a deployed environment.
"""

import asyncio
import json
import multiprocessing
import os
import secrets
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from cryptography.fernet import Fernet

from app.auth import SESSION_COOKIE
from app.config import Settings, get_settings

ROOT = Path(__file__).resolve().parents[2]
DATA = json.loads((ROOT / "automation/Input/InlineBAReview.Json").read_text())


def serve(settings):
    import uvicorn

    import app.config
    from app.agents.inline_business_analyst import (
        InlineBusinessAnalyst,
        stable_output,
        validate_output,
    )
    from app.ba_review_models import BAReviewOutput

    async def synthetic(self, request, sections, sources, limitations, focus=None):
        await asyncio.sleep(1)
        case = next(
            (item for item in DATA["cases"] if item["document"] == request.description), None
        )
        if case:
            output = BAReviewOutput.model_validate(case["output"])
        else:
            revised = json.loads(json.dumps(DATA["cases"][6]["output"]))
            revised.update(
                readiness_status="READY_FOR_BA_REVIEW",
                findings=[],
                business_questions=[],
                calculations=[],
                dependencies=[],
            )
            revised["requirements"][0].update(
                readiness="READY_FOR_BA_REVIEW",
                description=request.description,
                source_references=[
                    dict(source_id="BRD", section_id=sections[0]["id"], quote=sections[0]["text"])
                ],
            )
            output = BAReviewOutput.model_validate(revised)
        return stable_output(validate_output(output, sections, sources))

    InlineBusinessAnalyst.analyse = synthetic
    # Substitute provider outputs only inside the new revision orchestration. The existing
    # input-validation scenarios continue exercising the original provider/receipt guards.
    from contextvars import ContextVar
    from types import SimpleNamespace

    from app.agents.business_analyst import BusinessAnalystAgent
    from app.agents.requirements_validation import RequirementsValidationAgent
    from app.services.ba_reviews import BAReviews

    revision_context = ContextVar("revision_fixture", default=False)
    original_revalidate = BAReviews.execute_revalidation
    original_ba, original_alignment = (
        BusinessAnalystAgent.review,
        RequirementsValidationAgent.assess,
    )

    async def revalidate(self, *args):
        token = revision_context.set(True)
        try:
            await original_revalidate(self, *args)
        finally:
            revision_context.reset(token)

    async def ba_report(self, request):
        if not revision_context.get():
            return await original_ba(self, request)
        report = dict(
            summary="Synthetic updated BRD business assessment",
            outcome="ready_for_business_review",
            assessed_at="2026-10-21T00:00:00Z",
            scope=["Reviewed updated BRD"],
        )
        return SimpleNamespace(outcome=report["outcome"], model_dump=lambda **kwargs: report)

    async def alignment_report(self, request):
        if not revision_context.get():
            return await original_alignment(self, request)
        report = dict(status="aligned", message="Synthetic updated-source alignment")
        return SimpleNamespace(status="aligned", model_dump=lambda **kwargs: report)

    BAReviews.execute_revalidation = revalidate
    BusinessAnalystAgent.review = ba_report
    RequirementsValidationAgent.assess = alignment_report
    app.config.get_settings = lambda: settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: settings
    uvicorn.run(app, host="127.0.0.1", port=8128, log_level="warning")


def browser_check(password):
    import httpx
    from playwright.sync_api import expect, sync_playwright

    base = "http://127.0.0.1:8128"
    with httpx.Client(base_url=base) as client:
        assert (
            client.post(
                "/api/auth/login", json={"username": "ba-acceptance", "password": password}
            ).status_code
            == 200
        )
        project = client.post(
            "/api/sdlc/projects", json={"name": "Inline BA browser fixture"}
        ).json()["id"]
        session_cookie = f"{SESSION_COOKIE}={client.cookies.get(SESSION_COOKIE)}"
        assert (
            client.post(
                f"/api/sdlc/projects/{project}/artifacts/requirements-input", json=DATA["source"]
            ).status_code
            == 201
        )
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/login")
        page.locator("#username").fill("ba-acceptance")
        page.locator("#password").fill(password)
        page.locator("#login-button").click()
        page.wait_for_url("**/select-project")
        page.evaluate(
            '(id) => sessionStorage.setItem("sdlc-active-project:ba-acceptance", id)', project
        )
        page.goto(base + "/sdlc?phase=business-approval")
        workspace = page.locator("#ba-inline-workspace")
        expect(workspace).to_be_visible()
        expect(page.locator("#ba-agent-validate")).to_be_disabled()
        workspace.get_by_role("button", name="Generate AI suggestions", exact=True).click()
        finding = workspace.locator("[data-finding-id]")
        expect(finding).to_have_count(1, timeout=15000)
        expect(page.locator("#ba-agent-validate")).to_be_enabled()
        expect(page.locator("#project-lifecycle")).to_be_hidden()
        expect(page.locator("#ba-business-documents")).to_be_hidden()
        finding.click()
        expect(
            workspace.get_by_role("button", name="Previous suggestion", exact=True)
        ).to_be_disabled()
        expect(workspace.get_by_role("button", name="Next suggestion", exact=True)).to_be_disabled()
        expect(workspace.locator(".ba-review-stats")).to_contain_text("Need attention")
        expect(workspace.locator("#ba-original-source")).to_contain_text(
            DATA["source"]["content"]["document"]
        )
        workspace.get_by_role("button", name="View source · BRD L0001").click()
        workspace.locator("#ba-finding-comment").fill(DATA["comment"])
        workspace.get_by_role("button", name="Decline suggestion", exact=True).click()
        expect(workspace.locator(".ba-suggestion-status")).to_contain_text("Declined")
        page.reload()
        expect(workspace.locator(".ba-suggestion-status")).to_contain_text("Declined")
        workspace.locator("[data-finding-id]").click()
        workspace.get_by_text("Saved BA feedback (1)", exact=True).click()
        expect(workspace.locator(".ba-saved-feedback")).to_contain_text(DATA["comment"])
        workspace.get_by_text("Filter suggestions", exact=True).click()
        workspace.get_by_label("Review status", exact=True).select_option("REJECTED")
        expect(workspace.locator("[data-finding-id]")).to_have_count(1)
        for width in (1440, 768, 390):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            if width == 1440:
                columns = workspace.locator(".ba-inline-grid").evaluate(
                    "element => getComputedStyle(element).gridTemplateColumns.split(' ').length"
                )
                assert columns == 1, (
                    f"Expected full-width suggestion list above BRD review, got {columns}"
                )
                expect(workspace.locator(".ba-review-detail")).to_contain_text(
                    "1. What the BRD says"
                )
                expect(workspace.locator(".ba-review-detail")).to_contain_text(
                    "2. What AI suggests and why"
                )
                expect(workspace.locator(".ba-suggestion-row")).to_contain_text(
                    "Your decision on this suggestion"
                )
            page.screenshot(path=f"/tmp/ba-inline-review-{width}.png", full_page=True)
        expect(page.locator("#ba-feedback-rework #ba-signoff-comment")).to_have_count(1)
        expect(page.locator("#lifecycle-decision")).to_be_hidden()
        expect(
            page.locator("#ba-feedback-rework").get_by_role(
                "button", name="Sign off for story drafting", exact=True
            )
        ).to_be_enabled()
        expect(
            page.locator("#ba-feedback-rework").get_by_role(
                "button", name="Request changes", exact=True
            )
        ).to_be_visible()
        expect(
            page.locator("#ba-feedback-rework").get_by_role(
                "button", name="Continue review", exact=True
            )
        ).to_have_count(0)
        page.locator("#ba-signoff-comment").fill(
            "Synthetic BA verifies original source and records explicit sign-off."
        )
        page.get_by_role("button", name="Sign off for story drafting").click()
        expect(page.locator("#ba-feedback-rework")).to_contain_text("Signed off by ba-acceptance")
        page.reload()
        expect(page.locator("#ba-feedback-rework")).to_contain_text("Signed off by ba-acceptance")
        expect(page.locator("#ba-business-documents")).to_be_visible()
        with page.expect_download() as downloaded:
            page.get_by_role("link", name="Download all business documents", exact=True).click()
        assert downloaded.value.suggested_filename == "ba-review-v1-business-documents.zip"
        expect(page.locator("#ba-open-backlog")).to_be_visible()
        page.locator("#ba-open-backlog").click()
        expect(page.locator("#backlog-create-story")).to_be_enabled()
        page.locator("#backlog-create-story").click()
        form = page.locator("#lifecycle-item-form")
        expect(form.locator('[name="kind"]')).to_have_value("story")
        form.locator('[name="title"]').fill(DATA["backlog_story"]["title"])
        form.locator('[name="description"]').fill(DATA["backlog_story"]["description"])
        form.get_by_role("button", name="Save story", exact=True).click()
        expect(
            page.locator(".backlog-story-card", has_text=DATA["backlog_story"]["title"])
        ).to_be_visible()
        assert "phase=backlog" in page.url
        page.reload()
        expect(
            page.locator(".backlog-story-card", has_text=DATA["backlog_story"]["title"])
        ).to_be_visible()
        page.screenshot(path="/tmp/ba-approved-backlog-story.png", full_page=True)
        # Exercise the new final BRD update through the real UI, source storage and validation.
        revised_project = page.request.post(
            base + "/api/sdlc/projects", data={"name": "Updated BRD browser fixture"}
        ).json()["id"]
        saved = page.request.post(
            base + f"/api/sdlc/projects/{revised_project}/artifacts/requirements-input",
            data=DATA["source"],
        )
        assert saved.status == 201
        page.evaluate(
            "id => sessionStorage.setItem('sdlc-active-project:ba-acceptance', id)", revised_project
        )
        page.goto(base + "/sdlc?phase=business-approval&review=suggestions")
        workspace.get_by_role("button", name="Generate AI suggestions", exact=True).click()
        expect(workspace.locator("[data-finding-id]")).to_have_count(1, timeout=15000)
        update = workspace.get_by_role("button", name="Create updated BRD & revalidate", exact=True)
        expect(update).to_be_disabled()
        workspace.locator("[data-finding-id]").click()
        workspace.locator("#ba-finding-comment").fill(
            "Accept this synthetic proposal for BRD revalidation."
        )
        workspace.get_by_role("button", name="Accept suggestion", exact=True).click()
        expect(workspace.locator(".ba-suggestion-status")).to_have_text("Accepted as draft")
        expect(update).to_be_enabled()
        update.click()
        expect(page.locator("#ba-updated-brd")).to_contain_text(
            "Updated BRD v2 is saved", timeout=15000
        )
        expect(page.locator(".ba-analysis-state")).to_have_text(
            "Ready for BA review", timeout=15000
        )
        expect(page.locator("#ba-updated-brd")).to_contain_text("Updated BRD reassessed")
        with page.expect_download() as revised_download:
            page.get_by_role("link", name="Download updated BRD", exact=True).click()
        text = Path(revised_download.value.path()).read_text()
        assert DATA["cases"][6]["output"]["findings"][0]["suggested_requirement_text"] in text
        state = page.request.get(base + f"/api/sdlc/projects/{revised_project}/lifecycle").json()
        assert state["baseline"] == 2 and not state["backlog_drafting"]["signed_off"]
        assert set(state["approval_context"]["assessments"]) == {"business_analysis", "alignment"}
        page.screenshot(path="/tmp/updated-brd-revalidation.png", full_page=True)
        assert not errors, errors
        browser.close()
    print("LIVE_BA_INLINE_BROWSER_PASSED", flush=True)
    return session_cookie


def main():
    with tempfile.TemporaryDirectory(prefix="ba-review-acceptance-") as directory:
        root = Path(directory)
        password = secrets.token_urlsafe(24)
        settings = Settings(
            _env_file=None,
            browser_login_enabled=True,
            app_username="ba-acceptance",
            app_password=password,
            session_secret=secrets.token_urlsafe(48),
            user_database_path=root / "users.db",
            organizational_memory_path=root / "memory.db",
            organizational_memory_encryption_key=Fernet.generate_key().decode(),
            log_file_path=root / "app.jsonl",
        )
        process = multiprocessing.get_context("fork").Process(target=serve, args=(settings,))
        process.start()
        try:
            for _ in range(80):
                try:
                    urllib.request.urlopen("http://127.0.0.1:8128/health", timeout=1)
                    break
                except Exception:
                    time.sleep(0.25)
            session_cookie = browser_check(password)
            env = os.environ | {
                "QUALITY_LIFECYCLE_BASE_URL": "http://127.0.0.1:8128",
                "ROLE_TEST_ADMIN_USER": "ba-acceptance",
                "ROLE_TEST_ADMIN_PASSWORD": password,
                "API_AUTH_TOKEN": "",
                "API_SESSION_COOKIE": session_cookie,
            }
            subprocess.run(
                [
                    "dotnet",
                    "test",
                    "automation/QualityLifecycle.Automation.csproj",
                    "--no-restore",
                    "--filter",
                    "FullyQualifiedName~SourceGroundedInlineBAReview|"
                    "FullyQualifiedName~UpdatedBRDAfterBAReview|"
                    "FullyQualifiedName~HumanGovernedProjectLifecycle|"
                    "FullyQualifiedName~BAAgentBRDInputValidation",
                    "--logger",
                    "trx;LogFileName=inline-ba-review.trx",
                    "--results-directory",
                    "/tmp/ba-review-bdd-results",
                ],
                env=env,
                cwd=ROOT,
                check=True,
            )
        finally:
            process.terminate()
            process.join(timeout=10)


if __name__ == "__main__":
    main()
