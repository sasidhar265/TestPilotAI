"""Sign-in project choice, access failures and recovery in the rendered browser UI."""

import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from test_mobile_navigation_browser import mobile_route

from app.roles import capabilities
from app.services.project_lifecycle import ProjectLifecycle
from app.services.project_work_items import ProjectWorkItems
from app.services.sdlc import SDLCStore

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check"
)


@pytest.fixture
def selection_browser(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    store = SDLCStore(tmp_path / "memory.db")
    control = {"failure": None, "role": "admin", "created": 0, "reject_login": False}
    static = Path(__file__).parents[1] / "app/static"

    def route(request):
        path = urlparse(request.request.url).path
        if path in {"/select-project", "/login"}:
            file = static / ("select-project.html" if path == "/select-project" else "login.html")
            request.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/auth/profile":
            if control["failure"] == "expired":
                request.fulfill(status=401, json={"detail": "Expired"})
            else:
                request.fulfill(
                    json={
                        "username": "reviewer",
                        "display_name": "Review account",
                        "role": control["role"],
                        "is_admin": control["role"] == "admin",
                        "capabilities": capabilities(control["role"]),
                    }
                )
        elif path == "/api/auth/login":
            request.fulfill(
                status=401 if control["reject_login"] else 200,
                json={"detail": "Invalid credentials"}
                if control["reject_login"]
                else {"authenticated": True},
            )
        elif path == "/api/auth/logout":
            request.fulfill(json={"authenticated": False})
        elif path == "/api/sdlc/projects":
            if control["failure"] == "network":
                request.abort("internetdisconnected")
            elif control["failure"] == "malformed":
                request.fulfill(body="Service unavailable", content_type="text/html")
            elif control["failure"] == "service":
                request.fulfill(status=503, json={"detail": "Unavailable"})
            elif request.request.method == "POST":
                control["created"] += 1
                request.fulfill(
                    status=201,
                    json=store.create(request.request.post_data_json["name"], "reviewer"),
                )
            else:
                request.fulfill(json=store.projects("reviewer"))
        elif path.startswith("/api/sdlc/runs/"):
            request.fulfill(json=store.run(path.split("/")[-1], "reviewer"))
        elif path.startswith("/api/sdlc/projects/"):
            parts = path.removeprefix("/api/sdlc/projects/").split("/")
            if control["failure"] in {"revoked", "deleted"} and len(parts) == 1:
                request.fulfill(
                    status=403 if control["failure"] == "revoked" else 404,
                    json={"detail": "Unavailable"},
                )
            elif len(parts) == 1:
                request.fulfill(json=store.snapshot(parts[0], "reviewer"))
            elif parts[1] == "lifecycle":
                request.fulfill(
                    json=ProjectLifecycle(store).snapshot(parts[0], "reviewer", control["role"])
                )
            elif parts[1] == "work-items":
                request.fulfill(json=ProjectWorkItems(store).list(parts[0], "reviewer"))
            else:
                request.fulfill(json={})
        else:
            mobile_route(request)

    with pw.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("**/*", route)
        yield page, store, control
        browser.close()


def test_relogin_does_not_restore_saved_project_workflow(selection_browser):
    page, store, _ = selection_browser
    project = store.create("Session cleanup", "reviewer")

    def sign_in():
        page.locator("#username").fill("reviewer")
        page.locator("#password").fill("SyntheticPassword123!")
        page.locator("#login-button").click()
        page.wait_for_url("**/select-project")
        page.locator("#project-choice").select_option(project["id"])
        page.locator("#project-continue").click()
        page.wait_for_function("document.documentElement.dataset.projectContext === 'ready'")

    page.goto("http://localhost/login")
    sign_in()
    page.evaluate("document.getElementById('description').value = 'Previous confidential document'")
    draft = page.evaluate("window.exportTestingWorkspace()")
    draft["sourceAttachment"] = {"name": "previous.pdf", "size": 100}
    draft["attachmentSource"] = {"uploaded_brd_receipt": "previous-receipt"}
    store.save(project["id"], "reviewer", "workflow", draft, 0, [])
    page.evaluate("draft => window.restoreTestingWorkspace(draft)", draft)
    page.locator("#profile-toggle").click()
    page.locator("#logout").click()
    page.wait_for_url("**/login")
    assert page.evaluate("sessionStorage.getItem('quality-workspace-draft:v1:reviewer')") is None
    sign_in()
    assert page.locator("#description").input_value() == ""
    assert page.locator("#file-preview").is_hidden()
    assert page.locator("#requirements-validation-report").is_hidden()
    page.reload()
    page.wait_for_function("document.documentElement.dataset.projectContext === 'ready'")
    assert page.locator("#description").input_value() == ""
    assert page.locator("#file-preview").is_hidden()


def test_sign_in_requires_explicit_project_choice_and_hides_workspace_controls(selection_browser):
    page, store, control = selection_browser
    project = store.create("Quotation delivery", "reviewer")
    page.goto("http://localhost/login")
    page.evaluate("""() => {
        sessionStorage.setItem('sdlc-active-project:reviewer', 'previous-session');
        sessionStorage.setItem('quality-workspace-draft:v1:reviewer', 'previous-draft');
    }""")
    page.locator("#username").fill("reviewer")
    page.locator("#password").fill("SyntheticPassword123!")
    page.locator("#login-button").click()
    page.wait_for_url("**/select-project")
    assert page.evaluate("sessionStorage.getItem('sdlc-active-project:reviewer')") is None
    assert page.evaluate("sessionStorage.getItem('quality-workspace-draft:v1:reviewer')") is None
    page.locator("#project-choice").select_option(project["id"])
    assert page.url.endswith("/select-project")
    page.locator("#project-continue").click()
    page.wait_for_url("**/sdlc")
    page.wait_for_function("document.documentElement.dataset.projectContext === 'ready'")
    assert page.evaluate("window.sdlcCurrentProject().id") == project["id"]
    assert page.locator(".sdlc-project-controls").is_hidden()
    assert page.locator("#sdlc-status").is_hidden()
    assert page.locator(".topbar").get_by_text("Quotation delivery", exact=False).count() == 0
    page.reload()
    page.wait_for_function("document.documentElement.dataset.projectContext === 'ready'")
    assert page.evaluate("window.sdlcCurrentProject().id") == project["id"]
    page.locator("#profile-toggle").click()
    page.get_by_role("link", name="Change project", exact=True).click()
    page.locator("#project-picker").wait_for()
    assert page.url.endswith("/sdlc")
    page.locator("#project-cancel").click()
    page.locator("#project-picker").wait_for(state="detached")
    assert page.evaluate("window.sdlcCurrentProject().id") == project["id"]


@pytest.mark.parametrize("failure", ["network", "malformed", "service"])
def test_load_failure_can_retry_without_opening_workspace(selection_browser, failure):
    page, store, control = selection_browser
    store.create("Available project", "reviewer")
    control["failure"] = failure
    page.goto("http://localhost/select-project")
    page.locator("#selection-retry").wait_for()
    assert page.locator("#selection-status").get_attribute("data-error") == "true"
    assert page.locator("#project-selection").is_hidden()
    control["failure"] = None
    page.locator("#selection-retry").click()
    page.locator("#project-selection").wait_for()
    assert page.locator("#project-continue").is_disabled()


@pytest.mark.parametrize("failure", ["revoked", "deleted"])
def test_selection_rechecks_access_and_can_recover(selection_browser, failure):
    page, store, control = selection_browser
    project = store.create("Available project", "reviewer")
    page.goto("http://localhost/select-project")
    page.locator("#project-choice").select_option(project["id"])
    control["failure"] = failure
    page.locator("#project-continue").click()
    page.locator("#selection-retry").wait_for()
    assert page.url.endswith("/select-project")
    assert page.evaluate("sessionStorage.getItem('sdlc-active-project:reviewer')") is None
    control["failure"] = None
    page.locator("#selection-retry").click()
    page.locator("#project-choice").select_option(project["id"])
    page.locator("#project-continue").click()
    page.wait_for_url("**/sdlc")


def test_empty_account_can_create_once_and_open_project(selection_browser):
    page, store, control = selection_browser
    page.goto("http://localhost/select-project")
    page.locator("#project-empty").wait_for()
    assert page.locator("#project-create-panel").is_visible()
    page.locator("#project-name").fill("   ")
    page.locator("#project-create-button").click()
    assert (
        page.locator("#selection-status").inner_text() == "Enter a project name before continuing."
    )
    assert control["created"] == 0
    page.locator("#project-name").fill("Quotation delivery")
    page.locator("#project-create-button").click()
    page.wait_for_url("**/sdlc")
    assert control["created"] == 1
    assert store.projects("reviewer")[0]["name"] == "Quotation delivery"


def test_empty_developer_account_explains_missing_access(selection_browser):
    page, _, control = selection_browser
    control["role"] = "developer"
    page.goto("http://localhost/select-project")
    page.locator("#project-empty").wait_for()
    assert page.locator("#project-create-panel").is_hidden()
    assert "administrator or project owner" in page.locator("#project-empty-help").inner_text()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")


def test_expired_session_returns_to_sign_in(selection_browser):
    page, _, control = selection_browser
    control["failure"] = "expired"
    page.goto("http://localhost/select-project")
    page.wait_for_url("**/login?reason=expired")
    assert "session expired" in page.locator("#login-status").inner_text()


def test_direct_workspace_without_context_requires_selection(selection_browser):
    page, store, _ = selection_browser
    store.create("Available project", "reviewer")
    page.goto("http://localhost/sdlc")
    page.wait_for_url("**/select-project")
    page.locator("#project-choice").wait_for()


def test_invalid_credentials_do_not_open_project_selection(selection_browser):
    page, _, control = selection_browser
    control["reject_login"] = True
    page.goto("http://localhost/login")
    page.locator("#username").fill("reviewer")
    page.locator("#password").fill("InvalidPassword123!")
    page.locator("#login-button").click()
    page.locator("#auth-overlay").wait_for()
    assert page.url.endswith("/login")
    assert "incorrect" in page.locator("#auth-error-message").inner_text()


def test_blocked_session_storage_keeps_selection_open_with_actionable_error(selection_browser):
    page, store, _ = selection_browser
    project = store.create("Available project", "reviewer")
    page.add_init_script("""Storage.prototype.setItem = () => {
        throw new DOMException('Blocked for fixture', 'SecurityError');
    };""")
    page.goto("http://localhost/select-project")
    page.locator("#project-choice").select_option(project["id"])
    page.locator("#project-continue").click()
    page.locator("#selection-retry").wait_for()
    assert "Allow storage for this site" in page.locator("#selection-status").inner_text()
    assert page.url.endswith("/select-project")


def test_stale_workspace_context_returns_to_available_project_list(selection_browser):
    page, store, _ = selection_browser
    store.create("Available project", "reviewer")
    page.add_init_script("sessionStorage.setItem('sdlc-active-project:reviewer', 'deleted');")
    page.goto("http://localhost/sdlc")
    page.wait_for_url("**/select-project?reason=unavailable")
    page.locator("#project-selection").wait_for()
    assert "previous workspace" in page.locator("#selection-status").inner_text()


def test_shared_appearance_persists_from_project_choice_into_workspace(selection_browser):
    page, store, _ = selection_browser
    project = store.create("Quotation delivery", "reviewer")
    page.goto("http://localhost/select-project")
    page.locator("#project-choice").wait_for()
    assert page.locator("h1").count() == 1
    assert page.locator("#selection-title").evaluate("e => e === document.activeElement")
    page.keyboard.press("Tab")
    assert page.locator("#project-choice").evaluate("e => e === document.activeElement")
    for theme in ("dark", "light"):
        page.locator("#theme-gear").click()
        page.locator(f'[data-theme-option="{theme}"]').click()
        assert page.locator("html").get_attribute("data-theme") == theme
        for width in (390, 768, 1440):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            assert page.locator("#project-choice").bounding_box()["height"] == 44
            assert page.locator("#project-continue").bounding_box()["height"] >= 44
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(
                path=f"/tmp/project-selection-{theme}-{width}.png",
                full_page=True,
                animations="disabled",
            )
    page.locator("#theme-gear").click()
    page.locator('[data-theme-option="dark"]').click()
    page.reload()
    page.locator("#project-choice").wait_for()
    assert page.locator("html").get_attribute("data-theme") == "dark"
    page.locator("#project-choice").select_option(project["id"])
    page.locator("#project-continue").click()
    page.wait_for_url("**/sdlc")
    page.locator('html[data-project-context="ready"]').wait_for(state="attached")
    assert page.locator("html").get_attribute("data-theme") == "dark"


def test_required_project_dialog_traps_focus_and_does_not_dismiss_before_selection(
    selection_browser,
):
    page, store, _ = selection_browser
    store.create("Quotation delivery", "reviewer")
    page.goto("http://localhost/select-project")
    page.locator("#project-choice").wait_for()
    dialog = page.locator("#project-picker")
    assert dialog.evaluate("e => e.matches(':modal')")
    assert page.locator("#project-cancel").is_hidden()
    page.keyboard.press("Escape")
    assert dialog.is_visible()
    assert "Choose a project" in page.locator("#selection-status").inner_text()
    page.mouse.click(1, 1)
    assert dialog.is_visible()
    for _ in range(12):
        page.keyboard.press("Tab")
        assert dialog.evaluate("e => e.contains(document.activeElement)")
    page.locator("#theme-gear").click()
    page.locator("#theme-menu").wait_for()
    page.keyboard.press("Escape")
    assert dialog.is_visible()
    assert page.locator("#theme-menu").is_hidden()


def test_switch_project_popup_cancels_without_losing_work_and_does_not_leak_drafts(
    selection_browser,
):
    page, store, _ = selection_browser
    first = store.create("First project", "reviewer")
    second = store.create("Second project", "reviewer")
    page.goto("http://localhost/select-project")
    page.locator("#project-choice").select_option(first["id"])
    page.locator("#project-continue").click()
    page.wait_for_url("**/sdlc")
    page.locator('html[data-project-context="ready"]').wait_for(state="attached")
    page.locator("#description").fill("Unsaved first-project requirements must stay isolated.")
    page.locator("#profile-toggle").click()
    page.get_by_role("link", name="Change project", exact=True).click()
    page.locator("#project-choice").wait_for()
    assert page.url.endswith("/sdlc")
    assert page.locator("#theme-gear").count() == 1
    page.keyboard.press("Escape")
    page.locator("#project-picker").wait_for(state="detached")
    assert "first-project requirements" in page.locator("#description").input_value()
    assert page.locator("#profile-toggle").evaluate("e => e === document.activeElement")
    page.locator("#profile-toggle").click()
    page.get_by_role("link", name="Change project", exact=True).click()
    page.locator("#project-choice").select_option(second["id"])
    page.locator("#project-continue").click()
    page.wait_for_function("id => window.sdlcCurrentProject?.()?.id === id", arg=second["id"])
    page.locator('html[data-project-context="ready"]').wait_for(state="attached")
    assert page.locator("#description").input_value() == ""
    assert page.evaluate("sessionStorage.getItem('sdlc-active-project:reviewer')") == second["id"]


def test_switch_project_popup_loading_failure_can_retry_without_losing_context(selection_browser):
    page, store, _ = selection_browser
    project = store.create("Current project", "reviewer")
    page.goto("http://localhost/select-project")
    page.locator("#project-choice").select_option(project["id"])
    page.locator("#project-continue").click()
    page.wait_for_url("**/sdlc")
    page.locator('html[data-project-context="ready"]').wait_for(state="attached")
    page.route("**/select-project", lambda request: request.abort("internetdisconnected"))
    page.locator("#profile-toggle").click()
    change = page.get_by_role("link", name="Change project", exact=True)
    change.click()
    page.locator(".workspace-save-error").wait_for()
    assert "retry Change project" in page.locator(".workspace-save-error").inner_text()
    assert page.evaluate("window.sdlcCurrentProject().id") == project["id"]
    assert page.locator("#project-picker").count() == 0
    page.unroute("**/select-project")
    change.click()
    page.locator("#project-choice").wait_for()
    assert page.locator("#project-picker").evaluate("e => e.matches(':modal')")
