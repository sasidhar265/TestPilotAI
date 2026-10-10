"""Role-specific choices and navigation use the server-issued profile."""

import os
from urllib.parse import urlparse

import pytest
from test_mobile_navigation_browser import mobile_route

from app.roles import ROLE_LABELS, capabilities


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("role", ROLE_LABELS)
def test_role_choices_and_navigation(role):
    pw = pytest.importorskip("playwright.sync_api")
    access = capabilities(role)
    profile_requests = []

    def route(request):
        if urlparse(request.request.url).path == "/api/auth/profile":
            profile_requests.append(request.request.url)
            request.fulfill(
                json={
                    "username": "reviewer",
                    "display_name": "Role Reviewer",
                    "initials": "RR",
                    "role": role,
                    "is_admin": role == "admin",
                    "capabilities": access,
                }
            )
        else:
            mobile_route(request)

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://localhost/")
        pw.expect(page.locator("body")).to_have_attribute("data-role", role)
        assert len(profile_requests) == 1
        pw.expect(page.locator("#profile-name")).to_have_text("Role Reviewer")
        targets = page.locator("#output-target option").evaluate_all(
            "nodes => nodes.map(n => n.value)"
        )
        assert targets == (access["generation_targets"] or ["manual"])
        assert page.get_by_role("link", name="BA Agent", exact=True).count() == 0
        if role == "ba":
            pw.expect(page).to_have_url("http://localhost/")
            pw.expect(page.locator("#description")).to_be_visible()
            pw.expect(page.locator(".workflow-navigation")).to_be_visible()
            page.locator("#stage-tab-1").click()
            pw.expect(page.locator("#description")).to_be_visible()
            page.locator("a.brand").click()
            pw.expect(page.locator("#description")).to_be_visible()
            pw.expect(page.locator("#output-target")).to_be_hidden()
            pw.expect(page.locator("#stage-tab-3")).to_be_hidden()
            pw.expect(page.locator("#review-stories")).to_be_hidden()
            page.evaluate("window.navigateWorkspace('/?view=ba-agent')")
            pw.expect(page).to_have_url("http://localhost/?view=requirements")
            pw.expect(page.locator("#ba-review")).to_be_visible()
        else:
            pw.expect(page.locator("#stage-tab-4")).to_be_visible()
        if access["automation"]:
            pw.expect(page.locator("#stage-tab-6")).to_be_visible()
        else:
            pw.expect(page.locator("#stage-tab-6")).to_be_hidden()
            page.evaluate("window.navigateWorkspace('/?view=automation')")
            assert page.url in {
                "http://localhost" + access["home_path"],
                "http://localhost/?view=requirements",
            }
        if role == "non_functional_tester":
            assert page.locator("#manual-testing-type option").evaluate_all(
                "ns => ns.map(n=>n.value)"
            ) == ["performance", "database"]
        if role != "ba":
            page.evaluate("window.navigateWorkspace('/progress')")
            if access["automation"]:
                pw.expect(page.locator("#run-repository-bdd")).to_be_visible()
            else:
                pw.expect(page.locator("#run-repository-bdd")).to_be_hidden()
        if access["admin"]:
            pw.expect(page.locator(".admin-navigation")).to_be_visible()
            page.locator(".admin-navigation .nav-parent").click()
            pw.expect(page.locator('.admin-navigation a[href="/admin/users"]')).to_be_visible()
        else:
            pw.expect(page.locator(".admin-navigation")).to_be_hidden()
        page.goto("http://localhost/knowledge")
        pw.expect(page.locator("body")).to_have_attribute("data-role", role)
        pw.expect(page.locator(".workflow-navigation")).to_be_visible()
        visible = page.locator(".workflow-navigation [data-workflow-step]:visible")
        expected = 6 if access["automation"] else 4 if access["test_cases"] else 2
        pw.expect(visible).to_have_count(expected)
        assert len(profile_requests) == 2  # A fresh page has one shared profile request.
        pw.expect(page.locator("#profile-name")).to_have_text("Role Reviewer")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_admin_can_assign_and_edit_all_roles():
    from pathlib import Path

    pw = pytest.importorskip("playwright.sync_api")
    account = {
        "username": "jane",
        "display_name": "Jane Doe",
        "first_name": "Jane",
        "last_name": "Doe",
        "role": "functional_tester",
        "enabled": True,
        "managed": True,
    }
    updates = []

    def route(request):
        path = urlparse(request.request.url).path
        if path == "/admin/users":
            request.fulfill(
                body=(Path(__file__).parents[1] / "app/static/users.html").read_bytes(),
                content_type="text/html",
            )
        elif path == "/api/auth/profile":
            request.fulfill(
                json={
                    "username": "owner",
                    "display_name": "Admin",
                    "initials": "A",
                    "role": "admin",
                    "is_admin": True,
                    "capabilities": capabilities("admin"),
                }
            )
        elif path == "/api/admin/users":
            request.fulfill(json=[account])
        elif path == "/api/admin/users/jane":
            updates.append(request.request.post_data_json)
            account.update(updates[-1])
            request.fulfill(json=account)
        else:
            mobile_route(request)

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("**/*", route)
        page.goto("http://localhost/admin/users")
        pw.expect(page.get_by_role("button", name="Edit jane")).to_be_visible()
        assert page.locator("#user-role option").evaluate_all("ns=>ns.map(n=>n.value)") == list(
            ROLE_LABELS
        )
        page.get_by_role("button", name="Edit jane").click()
        pw.expect(page.locator("#user-role")).to_have_value("functional_tester")
        page.evaluate("document.fonts.ready")
        controls = page.locator('#create-user input:not([type="radio"]), #user-role').evaluate_all(
            "nodes => nodes.map(n => n.getBoundingClientRect().height)"
        )
        assert all(height == 44 for height in controls)
        role_top = page.locator("#user-role").bounding_box()["y"]
        access_top = page.locator(".account-radio-row").bounding_box()["y"]
        assert abs(role_top - access_top) < 1
        page.screenshot(path="/private/tmp/manage-users-aligned.png", full_page=True)
        page.select_option("#user-role", "automation_tester")
        page.get_by_role("button", name="Update user", exact=True).click()
        pw.expect(page.locator("#users-status")).to_contain_text("Existing sessions revoked")
        assert updates[0]["role"] == "automation_tester"
        pw.expect(page.locator("#users-list")).to_contain_text("Automation tester")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()
