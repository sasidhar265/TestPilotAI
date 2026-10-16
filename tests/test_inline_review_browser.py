"""Real BA and stakeholder UI handoff against an isolated configured server."""

import os
from uuid import uuid4

import pytest


@pytest.mark.skipif(not os.getenv("LIFECYCLE_BROWSER_BASE_URL"), reason="Isolated server required")
def test_inline_ba_review_stakeholder_approval_versions_and_traceability():
    pw = pytest.importorskip("playwright.sync_api")
    base = os.environ["LIFECYCLE_BROWSER_BASE_URL"]
    password = "Synthetic-inline-review-password-123"
    suffix = uuid4().hex[:10]
    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        admin = browser.new_context()
        response = admin.request.post(
            base + "/api/auth/login",
            data={
                "username": os.environ["ROLE_TEST_ADMIN_USER"],
                "password": os.environ["ROLE_TEST_ADMIN_PASSWORD"],
            },
        )
        assert response.status == 200
        usernames = {
            role: "inline-" + role + "-" + suffix for role in ["ba", "business_stakeholder"]
        }
        for role, username in usernames.items():
            response = admin.request.post(
                base + "/api/admin/users",
                data={
                    "username": username,
                    "password": password,
                    "role": role,
                    "first_name": "Inline",
                    "last_name": "Reviewer",
                },
            )
            assert response.status == 201, response.text()
        ba = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ba.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/login")
        page.locator('[name="username"]').fill(usernames["ba"])
        page.locator('[name="password"]').fill(password)
        page.locator('#login-form button[type="submit"]').click()
        page.wait_for_url(base + "/sdlc")
        page.locator("#sdlc-name").fill("Inline review " + suffix)
        page.locator("#sdlc-create button").click()
        page.wait_for_function("() => document.querySelector('#sdlc-project').value !== ''")
        identifier = page.locator("#sdlc-project").input_value()
        response = ba.request.post(
            base + f"/api/sdlc/projects/{identifier}/members",
            data={"username": usernames["business_stakeholder"]},
        )
        assert response.status == 201
        page.locator("#description").fill(
            "Synthetic BRD: reviewers must retain versioned clarification and approval evidence."
        )
        page.locator("#sdlc-save-requirements").click()
        page.wait_for_function(
            "() => document.querySelector('#sdlc-requirements-status').textContent"
            ".includes('v1 saved')"
        )
        form = page.locator("#lifecycle-item-form")
        form.locator('[name="title"]').fill("Reviewable requirement")
        form.locator('[name="description"]').fill("Original description for review")
        form.locator('[name="acceptance_criteria"]').fill(
            "The approved version is attributable to a human"
        )
        form.get_by_role("button", name="Save changes").click()
        page.locator(".record-row", has_text="Reviewable requirement").wait_for()
        page.wait_for_function(
            "() => document.querySelector('#record-context').textContent"
            ".includes('Draft / human review')"
        )
        page.locator("#record-comment-form textarea").fill(
            "Clarify what is recorded when approval is requested."
        )
        page.get_by_role("button", name="Add comment", exact=True).click()
        page.locator("#record-comments").get_by_text(
            "Clarify what is recorded", exact=False
        ).wait_for()
        form.locator('[name="description"]').fill(
            "Clarified description: preserve approver, timestamp and artifact versions."
        )
        form.get_by_role("button", name="Save changes").click()
        page.wait_for_function(
            "() => document.querySelector('#record-context').textContent.includes('v2')"
        )
        page.reload()
        page.locator(".record-row", has_text="Reviewable requirement").click()
        pw.expect(form.locator('[name="description"]')).to_have_value(
            "Clarified description: preserve approver, timestamp and artifact versions."
        )
        page.locator("#record-ai-panel summary").click()
        pw.expect(page.locator("#record-ai-suggestions")).to_contain_text("No current-baseline")
        page.keyboard.press("Control+k")
        pw.expect(page.locator(".workspace-command")).to_be_visible()
        page.locator("#workspace-command-input").fill("Reviewable requirement")
        page.keyboard.press("Enter")
        pw.expect(page.locator(".workspace-command")).not_to_be_visible()
        for stage in ["Business analyst validation", "Stakeholder approval"]:
            evidence = page.locator("#lifecycle-evidence")
            evidence.locator('[name="reference"]').fill("browser-fixture://inline-review")
            evidence.locator('[name="comment"]').fill(
                "Synthetic browser human attestation, not a live AI result"
            )
            evidence.get_by_role("button", name="Record evidence").click()
            page.wait_for_function(
                "() => !document.querySelector('#lifecycle-decision [value=approved]').disabled"
            )
            decision = page.locator("#lifecycle-decision")
            decision.locator('[name="comment"]').fill("Human reviewed current requirement version")
            decision.get_by_role("button", name="Complete stage").click()
            pw.expect(page.locator("#lifecycle-status")).to_contain_text(stage)
        stakeholder = browser.new_context(viewport={"width": 1440, "height": 1000})
        assert (
            stakeholder.request.post(
                base + "/api/auth/login",
                data={"username": usernames["business_stakeholder"], "password": password},
            ).status
            == 200
        )
        review = stakeholder.new_page()
        review.goto(base + "/sdlc")
        review.locator("#sdlc-project").select_option(identifier)
        review.locator(".record-row", has_text="Reviewable requirement").click()
        pw.expect(review.locator('#lifecycle-item-form [name="description"]')).to_be_disabled()
        pw.expect(review.locator("#record-comments")).to_contain_text("Clarify what is recorded")
        decision = review.locator("#lifecycle-decision")
        decision.locator('[name="comment"]').fill("Stakeholder approves clarified v2 requirements")
        decision.get_by_role("button", name="Approve this version").click()
        pw.expect(review.locator("#lifecycle-status")).to_contain_text("Backlog generation")
        response = ba.request.get(base + f"/api/sdlc/projects/{identifier}/work-items")
        records = response.json()
        assert records[0]["approved"] is True
        requirement_id = records[0]["id"]
        # Return to the BA phase to review and explicitly revise the approved requirement.
        page.reload()
        page.locator("#sdlc-phase-requirements").click()
        page.locator(".record-row", has_text="Reviewable requirement").click()
        pw.expect(page.locator("#record-context")).to_contain_text("Business approved")
        page.get_by_role("button", name="Revise requirement", exact=True).click()
        form.locator('[name="description"]').fill("Changed after stakeholder approval")
        form.get_by_role("button", name="Save changes").click()
        pw.expect(page.locator("#lifecycle-status")).to_contain_text("Requirements analysis")
        page.reload()
        page.locator(".record-row", has_text="Reviewable requirement").click()
        pw.expect(page.locator("#lifecycle-status")).to_contain_text("Requirements analysis")
        pw.expect(page.locator("#record-context")).to_contain_text("Draft / human review required")
        detail = ba.request.get(
            base + f"/api/sdlc/projects/{identifier}/work-items/{requirement_id}/detail"
        ).json()
        assert [version["version"] for version in detail["versions"]] == [3, 2, 1]
        assert detail["annotations"][0]["base_version"] == 1
        page.locator("#project-lifecycle").screenshot(path="/tmp/qls-inline-review-desktop.png")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        page.locator("#project-lifecycle").screenshot(path="/tmp/qls-inline-review-mobile.png")
        assert not errors
        browser.close()
