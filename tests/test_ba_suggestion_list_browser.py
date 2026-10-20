"""Readable suggestion selection preserves BRD context and keyboard navigation."""

import json
import os
from pathlib import Path

import pytest
from test_project_selection_browser import selection_browser as selection_browser

from app.models import GenerateRequest
from app.services.requirements_reviews import record_assessment

pytestmark = pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Browser check")


def test_suggestion_list_reads_vertically_and_selects_linked_detail(selection_browser, tmp_path):
    expect = pytest.importorskip("playwright.sync_api").expect
    page, store, _ = selection_browser
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    data = json.loads(Path("automation/Input/InlineBAReview.Json").read_text())
    case = data["cases"][0]
    project = store.create("Synthetic suggestion readability", "reviewer")["id"]
    source = GenerateRequest(description=case["document"])
    store.save(
        project,
        "reviewer",
        "requirements-input",
        {"document": source.description, "source_request": source.model_dump(mode="json")},
        0,
        [],
    )
    for kind in ("business_analysis", "alignment"):
        record_assessment(store, "reviewer", source, kind, {"summary": "Synthetic assessment"})
    output = case["output"]
    output["requirements"][0]["title"] = (
        "Confirm the quotation expiry date displayed to customers before accepting the quotation"
    )
    first = output["findings"][0]
    first["review_status"] = "PENDING"
    first["version"] = 1
    first["title"] = "Clarify when the quotation expiry date is calculated and shown to customers"
    second = first | {
        "finding_id": "synthetic-second-finding",
        "review_status": "CLARIFICATION_REQUESTED",
        "title": "Confirm which business stakeholder owns the quotation expiry rules",
    }
    output["findings"] = [first, second]
    review = {
        "id": "synthetic-readable-review",
        "project": project,
        "baseline": 1,
        "status": "completed",
        "revision": 1,
        "provider": "codex",
        "output": output,
        "knowledge_sources": [],
        "sections": [{"id": "L0001", "text": source.description}],
        "decisions": [],
    }
    page.route(
        f"**/api/sdlc/projects/{project}/ba-reviews",
        lambda route: route.fulfill(json={"run": review, "history": []}),
    )
    submitted = []

    def save_decision(route):
        payload = route.request.post_data_json
        submitted.append(payload)
        finding = next(
            item for item in output["findings"] if item["finding_id"] == payload["finding_id"]
        )
        finding["review_status"] = {
            "accept": "ACCEPTED_DRAFT",
            "reject": "REJECTED",
            "clarify": "CLARIFICATION_REQUESTED",
        }[payload["action"]]
        review["revision"] += 1
        review["decisions"].append(payload | {"actor": "reviewer", "created_at": "2026-10-21"})
        route.fulfill(json={"run": review})

    page.route(f"**/api/sdlc/projects/{project}/ba-reviews/{review['id']}/decisions", save_decision)
    page.add_init_script(
        "sessionStorage.setItem('sdlc-active-project:reviewer', " + json.dumps(project) + ")"
    )
    page.goto("http://localhost/sdlc?phase=business-approval&review=suggestions")
    cards = page.locator(".ba-suggestion-item")
    expect(cards).to_have_count(2)
    expect(cards.first).to_have_attribute("aria-current", "true")
    expect(cards.first.locator(".ba-suggestion-open")).to_have_text("Give feedback or decide ▾")
    expect(page.locator(".ba-suggestion-tile[open]")).to_have_count(0)
    expect(page.get_by_role("button", name="Accept suggestion", exact=True).first).to_be_hidden()
    for theme in ("light", "dark"):
        page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
        for width in (1440, 768, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            rows = page.locator(".ba-suggestion-row").evaluate_all("""rows => rows.map(row => {
              const box = row.getBoundingClientRect();
              return {top: box.top, bottom: box.bottom, width: box.width};
            })""")
            assert rows[1]["top"] >= rows[0]["bottom"]
            assert abs(rows[0]["width"] - rows[1]["width"]) < 1
            measurements = cards.evaluate_all("""cards => cards.map(card => {
              const rows = [...card.children].map(child => {
                const rect = child.getBoundingClientRect();
                return {top: rect.top, bottom: rect.bottom};
              });
              return {display: getComputedStyle(card).display,
                font: parseFloat(getComputedStyle(
                  card.querySelector('.ba-suggestion-title')).fontSize),
                fits: card.scrollWidth <= card.clientWidth + 1,
                vertical: rows.slice(1).every((row, index) => row.top >= rows[index].bottom - 1)};
            })""")
            assert all(
                item["display"] == "grid"
                and item["font"] >= 16
                and item["fits"]
                and item["vertical"]
                for item in measurements
            )
        page.locator(".ba-requirement-list").screenshot(
            path=str(tmp_path / f"suggestions-{theme}.png")
        )
    cards.nth(1).focus()
    cards.nth(1).press("Enter")
    expect(cards.nth(1)).to_have_attribute("aria-current", "true")
    for width in (1440, 768, 390, 320):
        page.set_viewport_size({"width": width, "height": 1000})
        geometry = (
            page.locator(".ba-suggestion-row")
            .nth(1)
            .locator(".ba-suggestion-row-decision > .ba-finding-actions")
            .evaluate("""group => {
            const parent = group.getBoundingClientRect();
            return [...group.children].map(button => {
                const box = button.getBoundingClientRect();
                return {top: box.top, bottom: box.bottom, left: box.left, right: box.right,
                    fits: box.left >= parent.left - 1 && box.right <= parent.right + 1};
            });
        }""")
        )
        assert len(geometry) == 3
        assert max(item["top"] for item in geometry) - min(item["top"] for item in geometry) < 1
        assert all(item["fits"] for item in geometry)
        assert all(geometry[index]["right"] <= geometry[index + 1]["left"] for index in (0, 1))

    expect(page.locator(".ba-context-panel h4")).to_have_text(second["title"])
    expect(page.locator(".ba-requirement-editor h4")).to_have_text(
        output["requirements"][0]["title"]
    )
    rows = page.locator(".ba-suggestion-row")
    cards.first.click()
    expect(rows.first.get_by_role("button", name="Accept suggestion", exact=True)).to_be_visible()
    rows.first.get_by_role("button", name="Accept suggestion", exact=True).click()
    assert not submitted  # A reason is required before either row decision can save.
    rows.first.locator(".ba-suggestion-row-decision textarea").fill(
        "Accept the first proposal as a draft."
    )
    rows.first.get_by_role("button", name="Accept suggestion", exact=True).click()
    expect(rows.first.locator(".ba-suggestion-status")).to_have_text("Accepted as draft")
    rows.nth(1).locator(".ba-suggestion-row-decision textarea").fill(
        "Decline the second proposal with this reason."
    )
    rows.nth(1).get_by_role("button", name="Decline suggestion", exact=True).click()
    expect(rows.nth(1).locator(".ba-suggestion-status")).to_have_text("Declined")
    assert [item["finding_id"] for item in submitted] == [first["finding_id"], second["finding_id"]]
    assert [item["action"] for item in submitted] == ["accept", "reject"]
    assert [item["revision"] for item in submitted] == [1, 2]
    assert [item["finding_version"] for item in submitted] == [1, 1]
    assert submitted[1]["comment"] == "Decline the second proposal with this reason."
    rows.nth(1).locator(".ba-suggestion-row-decision textarea").fill(
        "Business owner: please confirm the expiry rule."
    )
    expect(rows.nth(1).locator(".ba-suggestion-row-decision textarea")).to_have_value(
        "Business owner: please confirm the expiry rule."
    )
    rows.nth(1).get_by_role("button", name="Request feedback", exact=True).click()
    expect(rows.nth(1).locator(".ba-suggestion-status")).to_have_text("Awaiting clarification")
    assert submitted[-1]["comment"] == "Business owner: please confirm the expiry rule."
    assert submitted[-1]["action"] == "clarify"
    assert submitted[-1]["finding_id"] == second["finding_id"]
    cards.nth(1).click()
    expect(rows.nth(1).get_by_role("button", name="Request feedback", exact=True)).to_be_hidden()
    cards.nth(1).press("Enter")
    expect(rows.nth(1).get_by_role("button", name="Request feedback", exact=True)).to_be_visible()
    expect(rows.nth(1).locator(".ba-suggestion-row-decision textarea")).to_have_value(
        "Business owner: please confirm the expiry rule."
    )
    assert not errors
