"""Lifecycle navigation keeps AI drafts and accountable human handoffs visible."""

import json
import os

import pytest
from test_project_selection_browser import selection_browser as selection_browser

from app.lifecycle_workflow import PHASES


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_responsibilities_follow_navigation_and_survive_reload(selection_browser):
    page, store, _ = selection_browser
    project = store.create("Lifecycle navigation", "reviewer")
    page.add_init_script(
        "sessionStorage.setItem('sdlc-active-project:reviewer', " + json.dumps(project["id"]) + ")"
    )
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://localhost/sdlc")
    for phase in PHASES:
        page.locator(f"#sdlc-phase-{phase['id']}").click()
        page.wait_for_function(
            "id => document.querySelector('#sdlc-step-panel').dataset.phase === id",
            arg=phase["id"],
        )
        if phase["id"] == "requirements":
            assert page.locator("#sdlc-responsibilities").is_hidden()
            page.get_by_role("button", name="Requirements responsibilities and handoff information").click()
            assert page.locator("#sdlc-responsibilities").is_visible()
            page.keyboard.press("Escape")
            assert page.locator("#sdlc-responsibilities").is_hidden()
            page.locator("#requirements-info").click()
        else:
            assert page.locator("#requirements-info").is_hidden()
            assert page.locator("#sdlc-responsibilities").is_visible()
        assert (
            page.locator("#sdlc-ai-responsibility").inner_text() == phase["responsibilities"]["ai"]
        )
        assert (
            page.locator("#sdlc-human-responsibility").inner_text()
            == phase["responsibilities"]["human"]
        )
        assert (
            page.locator("#sdlc-handoff-artifacts li").all_text_contents()
            == phase["responsibilities"]["artifacts"]
        )
    page.reload()
    page.wait_for_function("document.querySelector('#sdlc-step-panel').dataset.phase === 'closure'")
    page.locator(".delivery-documentation summary").click()
    assert "validate and publish" in page.locator("#sdlc-documentation-policy").inner_text()
    for width in (390, 1440):
        page.set_viewport_size({"width": width, "height": 1000})
        assert page.locator("#sdlc-human-responsibility").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.screenshot(path="/tmp/delivery-responsibilities.png", full_page=True)
    assert not errors
