"""Backlog story authoring stays local to Backlog and persists source-linked drafts."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect
from test_delivery_pipeline_browser import choose_fixture_project
from test_inline_ba_review import FIXTURES, decision
from test_project_selection_browser import selection_browser as selection_browser

from app.agents.inline_business_analyst import (
    InlineBusinessAnalyst,
    source_sections,
    stable_output,
    validate_output,
)
from app.ba_review_models import BAReviewOutput, ReviewSignoff, ReviewStart
from app.config import Settings
from app.models import GenerateRequest
from app.sdlc_routes import WorkItemInput
from app.services.ba_reviews import BAReviews
from app.services.project_reviews import ProjectReviews
from app.services.project_work_items import ProjectWorkItems
from app.services.sdlc import SDLCError

pytestmark = pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Browser check")


def test_backlog_creates_lists_and_edits_stories_without_opening_qa(selection_browser, monkeypatch):
    page, store, control = selection_browser
    project = choose_fixture_project(page, store)
    control["role"] = "ba"
    case = FIXTURES["cases"][6]
    source = GenerateRequest(description=case["document"], llm_model="codex")
    store.save(
        project,
        "reviewer",
        "requirements-input",
        {"document": source.description, "source_request": source.model_dump(mode="json")},
        0,
        [],
    )
    output = stable_output(
        validate_output(
            BAReviewOutput.model_validate(case["output"]), source_sections(case["document"]), []
        )
    )
    monkeypatch.setattr(InlineBusinessAnalyst, "analyse", AsyncMock(return_value=output))
    service = BAReviews(store, Settings(organizational_memory_path=store.path))
    run, _ = service.start(project, "reviewer", "ba", ReviewStart(baseline=1), human=True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(
            lambda: asyncio.run(service.execute(project, "reviewer", run["id"]))
        ).result()
    run = service.snapshot(project, "reviewer")["run"]
    records = ProjectWorkItems(store)

    def work_items(route):
        path = urlparse(route.request.url).path
        try:
            if route.request.method == "POST":
                result = records.save(
                    project,
                    "reviewer",
                    "ba",
                    WorkItemInput.model_validate(route.request.post_data_json).model_dump(),
                )
                route.fulfill(status=201, json=result)
            elif path.endswith("/detail"):
                route.fulfill(
                    json=ProjectReviews(store).detail(
                        project, path.split("/")[-2], "reviewer", "ba"
                    )
                )
            else:
                route.fulfill(json=records.list(project, "reviewer"))
        except (SDLCError, PermissionError) as error:
            route.fulfill(status=409, json={"detail": str(error)})

    page.route(f"**/api/sdlc/projects/{project}/work-items**", work_items)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://localhost/sdlc?phase=backlog")
    expect(page.locator("#backlog-create-story")).to_be_disabled()
    expect(page.locator("#backlog-story-list")).to_contain_text("No user stories yet")
    assert page.get_by_role("link", name="Open story design", exact=True).count() == 0
    run = service.decide(project, "reviewer", "ba", run["id"], decision(run), human=True)
    service.signoff(
        project,
        "reviewer",
        "ba",
        run["id"],
        ReviewSignoff(
            revision=run["revision"], comment="BA confirms the source and reviewed findings."
        ),
        human=True,
    )
    page.reload()
    expect(page.locator("#backlog-create-story")).to_be_enabled()
    page.locator("#backlog-create-story").click()
    form = page.locator("#lifecycle-item-form")
    expect(form).to_be_visible()
    expect(form.locator('[name="kind"]')).to_have_value("story")
    form.locator('[name="title"]').fill("Quotation expiry story")
    form.locator('[name="description"]').fill(source.description)
    form.get_by_role("button", name="Save story", exact=True).click()
    cards = page.locator(".backlog-story-card")
    expect(cards).to_have_count(1)
    expect(cards.first).to_contain_text("Quotation expiry story")
    expect(page.locator("#backlog-save-status")).to_contain_text("Story saved")
    assert page.url.endswith("/sdlc?phase=backlog")
    assert page.locator("#backlog-created-stories").bounding_box()["y"] >= page.locator(
        "#backlog-story-handoff"
    ).evaluate("e => e.getBoundingClientRect().bottom")
    page.reload()
    expect(cards).to_have_count(1)
    expect(form).to_be_hidden()
    cards.get_by_role("button", name="Review or edit story").click()
    expect(form.locator('[name="title"]')).to_be_enabled()
    form.locator('[name="title"]').fill("Reviewed quotation expiry story")
    form.get_by_role("button", name="Save story", exact=True).click()
    expect(cards).to_have_count(1)
    expect(cards.first).to_contain_text("Reviewed quotation expiry story")
    expect(cards.first).to_contain_text("v2")
    page.reload()
    expect(cards.first).to_contain_text("Reviewed quotation expiry story")
    for width in (1440, 768, 390):
        page.set_viewport_size({"width": width, "height": 1000})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.screenshot(path=f"/tmp/backlog-stories-{width}.png", full_page=True)
    assert page.url.endswith("/sdlc?phase=backlog")
    assert not errors
