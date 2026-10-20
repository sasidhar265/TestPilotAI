"""Shared presentation contracts across actual page assets and responsive layouts."""

import os

import pytest
from test_mobile_navigation_browser import mobile_route
from test_project_selection_browser import selection_browser as selection_browser


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize(
    "name", ["index", "documentation", "knowledge", "logs", "users", "api-docs", "user-guide"]
)
def test_shared_headers_accessibility_and_card_geometry(name):
    playwright = pytest.importorskip("playwright.sync_api")
    paths = {
        "index": "/",
        "documentation": "/documentation",
        "knowledge": "/knowledge",
        "logs": "/logs",
        "users": "/admin/users",
        "api-docs": "/docs",
        "user-guide": "/static/user-guide.html",
    }
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("**/*", mobile_route)
        page.goto("http://localhost" + paths[name])
        assert page.locator("h1").count() == 1
        assert page.get_by_role("navigation", name="Breadcrumb", exact=True).count() == 1
        assert (
            page.locator(".workspace-breadcrumbs [aria-current=page]").inner_text()
            == page.locator("h1").inner_text()
        )
        assert page.locator(".topbar .page-intro, .topbar .users-intro").is_visible()
        page.screenshot(path=f"/tmp/qls-ui-{name}-desktop.png", full_page=True)
        page.keyboard.press("Tab")
        assert page.locator(".workspace-skip-link").evaluate("e => e === document.activeElement")
        page.keyboard.press("Enter")
        assert page.locator("main").evaluate("e => e === document.activeElement")
        card = page.locator(
            "main .panel:visible, main .knowledge-card:visible, main .section:visible"
        ).first
        if card.count():
            assert card.evaluate("e => getComputedStyle(e).borderRadius") == "14px"
        if name == "users":
            page.locator("#user-role").select_option("release_manager")
            assert "production approval" in page.locator("#role-help").inner_text()
        for theme in ["light", "dark"]:
            page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
            for width in [390, 1440]:
                page.set_viewport_size({"width": width, "height": 1000})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                assert page.locator(".workspace-breadcrumbs").is_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=f"/tmp/qls-ui-{name}-mobile-dark.png", full_page=True)
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_workspace_header_updates_and_multiselect_is_usable():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("**/*", mobile_route)
        page.goto("http://localhost/")
        page.evaluate("window.navigateWorkspace('/?view=stories', false)")
        assert page.locator(".workspace-breadcrumbs [aria-current=page]").inner_text() == "Stories"
        assert "acceptance criteria" in page.locator(".topbar .page-intro").inner_text()
        page.evaluate("window.navigateWorkspace('/sdlc', false)")
        # Verify the real record selector without inventing project state or credentials.
        height = page.locator("#lifecycle-item-form select[multiple]").evaluate(
            "e => getComputedStyle(e).minHeight"
        )
        assert height == "132px"
        assert page.locator("#lifecycle-timeline-panel").get_attribute("open") is None
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_sdlc_steps_support_keyboard_preview_and_url_restore():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("**/*", mobile_route)
        page.goto("http://localhost/sdlc")
        page.locator("#sdlc-phase-requirements").wait_for()
        assert page.locator("#sdlc-navigation #sdlc-phase-tabs a").count() == 8
        page.locator("#sdlc-phase-requirements").focus()
        page.keyboard.press("End")
        assert page.locator("#sdlc-phase-closure").evaluate("e => e === document.activeElement")
        page.keyboard.press("Enter")
        assert page.locator("#sdlc-step-heading").inner_text() == "Closure"
        assert "phase=closure" in page.url
        assert page.locator("#project-lifecycle").is_hidden()
        page.reload()
        page.locator("#sdlc-phase-closure").wait_for()
        assert page.locator("#sdlc-phase-closure").get_attribute("aria-current") == "page"
        page.locator("#sdlc-phase-closure").focus()
        page.keyboard.press("Home")
        page.keyboard.press("Enter")
        assert page.locator("#sdlc-step-heading").inner_text() == "Requirements"
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
def test_home_is_sdlc_with_shared_requirements_editor_and_contextual_tools():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", mobile_route)
        page.goto("http://localhost/")
        page.locator("#sdlc-phase-requirements").wait_for()
        assert page.url.endswith("/sdlc")
        assert page.locator("h1").inner_text() == "Requirements"
        assert page.locator(".sdlc-workspace > .sdlc-project-controls").is_hidden()
        assert page.locator(".sdlc-workspace > .panel-head").is_hidden()
        assert page.locator("#project-lifecycle").is_hidden()
        assert page.get_by_role("heading", name="Your project", exact=True).count() == 0
        assert page.locator("#sdlc-requirements-editor #description").is_visible()
        assert page.locator(".nav-specialist-tools").get_attribute("open") is None
        assert page.locator("#description").count() == 1
        page.locator("#description").fill("A saved draft must survive changing the workflow view.")
        page.locator("#sdlc-phase-backlog").click()
        assert page.locator("#description").is_hidden()
        assert page.locator("#sdlc-project").is_visible()
        page.locator("#sdlc-phase-requirements").click()
        assert page.locator("#description").input_value().startswith("A saved draft")
        page.evaluate("window.navigateWorkspace('/?view=requirements', false)")
        assert page.locator("#test-studio #description").is_visible()
        page.evaluate("window.navigateWorkspace('/sdlc?phase=requirements', false)")
        assert page.locator("#sdlc-requirements-editor #description").is_visible()
        assert page.locator("#description").input_value().startswith("A saved draft")
        assert page.locator(".nav-specialist-tools").get_attribute("open") is not None
        assert page.locator('.nav-specialist-tools a[href="/?view=test-cases"]').is_visible()
        for width in [390, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert not errors
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("engine", ["chromium", "webkit"])
def test_sidebar_sdlc_stages_close_mobile_drawer_and_restore_history(engine):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = getattr(runtime, engine).launch()
        page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", mobile_route)
        page.goto("http://localhost/sdlc?phase=development")
        playwright.expect(page.locator("h1")).to_have_text("Development")
        page.locator("#sidebar-toggle").tap()
        page.locator("#sdlc-phase-requirements").tap()
        playwright.expect(page.locator("h1")).to_have_text("Requirements")
        playwright.expect(page.locator("#sidebar-toggle")).to_have_attribute(
            "aria-expanded", "false"
        )
        assert "phase=requirements" in page.url
        assert page.locator("#project-lifecycle").is_hidden()
        assert page.locator("#sdlc-project").is_hidden()
        page.locator("#description").fill("Requirements draft survives sidebar navigation.")
        page.locator("#sidebar-toggle").tap()
        page.locator("#sdlc-phase-backlog").tap()
        playwright.expect(page.locator("h1")).to_have_text("Backlog")
        page.go_back()
        playwright.expect(page.locator("h1")).to_have_text("Requirements")
        assert page.locator("#description").input_value().startswith("Requirements draft")
        assert page.locator('#sdlc-navigation [aria-current="page"]').count() == 1
        page.reload()
        playwright.expect(page.locator("h1")).to_have_text("Requirements")
        assert page.locator("#sdlc-phase-requirements").get_attribute("aria-current") == "page"
        assert not errors
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize("width", [390, 1440])
def test_documents_nav_opens_saved_versions_and_survives_reload(tmp_path, width):
    from urllib.parse import urlparse

    from app.services.sdlc import SDLCStore

    playwright = pytest.importorskip("playwright.sync_api")
    store = SDLCStore(tmp_path / "documents.db")
    project = store.create("Documents browser fixture", "reviewer")["id"]
    store.save(project, "reviewer", "planning", {"document": "First saved plan"}, 0, [])
    store.save(project, "reviewer", "planning", {"document": "Revised saved plan"}, 1, [])

    def route(request):
        path = urlparse(request.request.url).path
        if path == "/api/sdlc/projects":
            request.fulfill(json=store.projects("reviewer"))
        elif path == f"/api/sdlc/projects/{project}":
            request.fulfill(json=store.snapshot(project, "reviewer"))
        else:
            mobile_route(request)

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route)
        page.goto("http://localhost/sdlc")
        if width < 1081:
            page.locator("#sidebar-toggle").click()
        page.locator("#sdlc-documents-link").click()
        playwright.expect(page.locator("h1")).to_have_text("Documents and version history")
        playwright.expect(page.locator("#sdlc-project")).to_be_visible()
        page.locator("#sdlc-project").select_option(project)
        playwright.expect(page.locator("#sdlc-document")).to_have_value("Revised saved plan")
        playwright.expect(page.locator("#sdlc-history .sdlc-history-item")).to_have_count(2)
        assert page.locator(".sdlc-artifact-ledger").get_attribute("open") is not None
        assert page.locator(".sdlc-sequence").is_hidden()
        assert page.locator("#project-lifecycle").is_hidden()
        assert page.locator('#sdlc-documents-link[aria-current="page"]').count() == 1
        page.reload()
        playwright.expect(page.locator("h1")).to_have_text("Documents and version history")
        playwright.expect(page.locator("#sdlc-document")).to_have_value("Revised saved plan")
        assert page.locator(".sdlc-artifact-ledger").get_attribute("open") is not None
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert not errors
        browser.close()


@pytest.mark.skipif(os.getenv("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check")
@pytest.mark.parametrize(
    "path",
    [
        "/sdlc?phase=requirements",
        "/sdlc?phase=business-approval",
        "/sdlc?phase=backlog",
        "/project-dashboard",
        "/knowledge",
        "/logs",
        "/admin/users",
        "/documentation",
    ],
)
def test_shared_text_actions_align_without_clipping(selection_browser, path):
    from test_delivery_pipeline_browser import choose_fixture_project

    from app.models import GenerateRequest

    page, store, _ = selection_browser
    project = choose_fixture_project(page, store)
    source = GenerateRequest(
        description="Synthetic quotation requirements for button layout checks."
    )
    store.save(
        project,
        "reviewer",
        "requirements-input",
        {
            "document": source.description,
            "source_request": source.model_dump(mode="json"),
        },
        0,
        [],
    )
    page.goto("http://localhost" + path)
    page.locator("h1").wait_for()
    selector = (
        "main :is(button.primary, button.secondary, button.stop, "
        "button.log-toolbar-action, a.button):visible"
    )
    for theme in ("light", "dark"):
        page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
        for width in (1440, 1280, 1024, 768, 701, 700, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            actions = page.locator(selector).evaluate_all("""elements => elements.map(element => {
                const box = element.getBoundingClientRect(), css = getComputedStyle(element);
                return {text: element.textContent.trim(), height: box.height,
                    x: box.x, y: box.y, right: box.right, bottom: box.bottom,
                    scroll: element.scrollHeight, client: element.clientHeight,
                    font: css.fontSize, line: css.lineHeight};
            })""")
            assert actions, path
            for action in actions:
                assert action["height"] >= 43.5, (path, width, action)
                assert action["scroll"] <= action["client"] + 1, (path, width, action)
                assert action["font"] == "13px", (path, width, action)
            for index, action in enumerate(actions):
                for other in actions[index + 1 :]:
                    overlap_x = min(action["right"], other["right"]) - max(action["x"], other["x"])
                    overlap_y = min(action["bottom"], other["bottom"]) - max(
                        action["y"], other["y"]
                    )
                    assert overlap_x <= 1 or overlap_y <= 1, (path, width, action, other)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
            page.screenshot(
                path=(
                    f"/tmp/button-alignment-{path.split('?')[0].replace('/', '-')}"
                    f"-{width}-{theme}.png"
                ),
                full_page=True,
            )
