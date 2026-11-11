"""Full-app UI regressions: real routes, scripts, security headers and persistence."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in full-app browser checks"
)


@pytest.fixture(scope="module")
def workspace_url(tmp_path_factory):
    directory = tmp_path_factory.mktemp("workspace-browser")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = os.environ | {"QUALITY_UI_TEST_DIRECTORY": str(directory)}
    with (directory / "server.log").open("w") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "browser_support:create_app",
                "--factory",
                "--app-dir",
                "tests",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "error",
            ],
            cwd=Path(__file__).parents[1],
            env=environment,
            stdout=output,
            stderr=output,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(150):
                if process.poll() is not None:
                    pytest.fail((directory / "server.log").read_text())
                try:
                    if httpx.get(url + "/api/live", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Isolated UI server did not become ready")
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.fixture
def live_page(workspace_url):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(workspace_url + "/login")
        page.locator("#username").fill("ui.admin")
        page.locator("#password").fill("Isolated-ui-password-123!")
        page.locator("#login-button").click()
        page.wait_for_url(workspace_url + "/")
        yield page, workspace_url
        browser.close()
        assert not errors, errors


def wait_ready(page):
    page.wait_for_function(
        "() => document.getElementById('ka-list').getAttribute('aria-busy') === 'false'"
    )


def review_and_publish(page):
    page.get_by_role("button", name="Review", exact=True).last.click()
    page.locator('#ka-review-form [name="note"]').fill(
        "Reviewed source evidence, stage scope and usage limitations."
    )
    page.locator('#ka-review-form [name="approve_reference_use"]').check()
    page.locator('#ka-review-form [type="submit"]').click()
    page.wait_for_function("() => !document.getElementById('ka-review').open")
    page.get_by_role("button", name="Publish to app", exact=True).last.click()
    page.wait_for_function(
        "() => document.getElementById('ka-status').textContent"
        ".includes('published to the application')"
    )


@pytest.mark.parametrize("width", [1440, 390])
def test_built_in_agent_function_board(live_page, width):
    page, url = live_page
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(url + "/agent-information?view=built-in")
    page.wait_for_function(
        "() => document.getElementById('agent-list').getAttribute('aria-busy') === 'false'"
    )
    assert page.locator(".agent-board-column-heading h3").all_text_contents() == [
        "Advice",
        "Builders",
        "Operators",
        "Custom agents",
    ]
    assert page.locator(".agent-board-agent").count() == 22
    ids = page.locator(".agent-board-agent").evaluate_all(
        "nodes => nodes.map(node => node.dataset.agentId)"
    )
    assert len(set(ids)) == 22
    assert page.locator(".agent-board-agent .agent-avatar").count() == 22
    assert page.locator('[data-board-category="custom"]').inner_text().endswith("No custom agents")
    if width > 1200:
        columns = page.locator(".agent-board-column").all()
        positions = [column.bounding_box() for column in columns]
        assert len({round(position["x"]) for position in positions}) == 4
        assert len({round(position["y"]) for position in positions}) == 1
        assert (
            page.locator("#agent-search").bounding_box()["x"]
            > page.locator("#agents-title").bounding_box()["x"]
        )
    assert page.locator(".agent-board-filters").bounding_box()["y"] >= (
        page.locator("#agent-search").bounding_box()["y"]
        + page.locator("#agent-search").bounding_box()["height"]
    )
    page.get_by_role("button", name="Advice", exact=True).click()
    assert page.locator(".agent-board-column").count() == 1
    assert page.locator(".agent-board-agent").count() == 7
    page.get_by_role("button", name="All agents", exact=True).click()
    page.locator("#agent-search").fill("input agent")
    assert page.locator(".agent-board-agent").count() == 1
    page.locator(".agent-board-agent").click()
    assert page.locator("#agent-detail-dialog").evaluate("node => node.open")
    page.locator("#close-agent-details").click()
    page.locator("#clear-agent-filters").click()
    page.get_by_role("button", name="New custom agent", exact=True).click()
    page.locator("#custom-agent-name").fill("Board custom specialist")
    page.locator("#custom-agent-purpose").fill(
        "Review application terminology and naming conventions"
    )
    page.locator("#custom-agent-instructions").fill(
        "Use approved application terminology to review documentation and labels."
    )
    page.locator('#custom-agent-form [type="submit"]').click()
    page.wait_for_function("() => !document.getElementById('custom-agent-dialog').open")
    assert "Board custom specialist" in page.locator('[data-board-category="custom"]').inner_text()
    assert "No custom agents" not in page.locator('[data-board-category="custom"]').inner_text()
    page.reload()
    page.wait_for_function(
        "() => document.getElementById('agent-list').getAttribute('aria-busy') === 'false'"
    )
    assert "Board custom specialist" in page.locator('[data-board-category="custom"]').inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390])
def test_knowledge_editor_publication_and_rollback(live_page, width):
    page, url = live_page
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(url + "/knowledge-agents")
    wait_ready(page)
    assert page.get_by_role("heading", name="Knowledge information", exact=True).count() == 1
    assert (
        page.locator(
            '#knowledge-navigation a[href="/knowledge?view=overview"] > span:last-child'
        ).inner_text()
        == "Knowledge"
    )
    assert page.locator('#ka-topics option[value="Architecture"]').count() == 1
    assert page.locator('#ka-topics option[value="Workflows"]').count() == 1
    page.get_by_role("button", name="Add knowledge").click()
    assert page.locator("#ka-editor-title").inner_text() == "Add application knowledge"
    fixture = json.loads(
        (Path(__file__).parents[1] / "automation/Input/KnowledgeAgents.Json").read_text()
    )["reference-contributor"]
    fixture["name"] += " " + uuid4().hex[:8]
    for field in [
        "name",
        "purpose",
        "domain",
        "profile",
        "source_reference",
        "instructions",
        "knowledge",
    ]:
        page.locator(f'#ka-form [name="{field}"]').fill(fixture[field])
    page.locator('#ka-form [name="stages"][value="stories"]').check()
    footer = page.locator("#ka-editor .ka-dialog-actions").bounding_box()
    assert footer["y"] + footer["height"] <= 900
    assert page.locator("#ka-editor").evaluate("node => node.scrollWidth <= node.clientWidth")
    if width > 650:
        assert (
            abs(
                page.locator('[name="profile"]').bounding_box()["y"]
                - page.locator('[name="source_reference"]').bounding_box()["y"]
            )
            < 1
        )
    page.locator('#ka-form [type="submit"]').click()
    page.wait_for_function("() => !document.getElementById('ka-editor').open")
    page.locator("#ka-search").fill(fixture["name"])
    review_and_publish(page)
    page.get_by_role("button", name="Edit draft", exact=True).click()
    page.locator('#ka-form [name="knowledge"]').fill(
        fixture["knowledge"] + " Additional source evidence."
    )
    page.locator('#ka-form [type="submit"]').click()
    page.wait_for_function("() => !document.getElementById('ka-editor').open")
    assert page.locator(".ka-badge").inner_text() == "Published v1"
    review_and_publish(page)
    assert page.locator(".ka-badge").inner_text() == "Published v2"
    page.get_by_role("button", name="View / history", exact=True).click()
    page.wait_for_selector(".ka-comparison")
    assert "1 definition fields differ" in page.locator(".ka-comparison-count").inner_text()
    assert "Additional source evidence." in page.locator(".ka-comparison-fields").inner_text()
    page.get_by_role("combobox", name="Version A", exact=True).select_option("2")
    assert "0 definition fields differ" in page.locator(".ka-comparison-count").inner_text()
    page.get_by_role("combobox", name="Version A", exact=True).select_option("1")
    assert page.locator(".ka-comparison-field").count() == 1
    page.get_by_label("Show unchanged fields", exact=True).check()
    assert page.locator(".ka-comparison-field").count() == 8
    page.get_by_role("button", name="Activate v1", exact=True).click()
    page.wait_for_function(
        "() => document.querySelector('.ka-badge').textContent === 'Published v1'"
    )
    page.get_by_role("button", name="Withdraw", exact=True).click()
    page.wait_for_function(
        "() => document.querySelector('.ka-badge').textContent === 'Not published'"
    )


def test_settings_logo_accepts_500_kb_and_rejects_larger_files(live_page):
    import io

    from PIL import Image

    page, url = live_page
    page.goto(url + "/settings")
    page.wait_for_function("() => !document.getElementById('appearance-fields').disabled")
    output = io.BytesIO()
    Image.new("RGB", (32, 32)).save(output, format="PNG")
    png = output.getvalue()
    page.locator("#settings-logo").set_input_files(
        {"name": "logo.png", "mimeType": "image/png", "buffer": png.ljust(500 * 1024, b"\0")}
    )
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent.startsWith('Logo ready')"
    )
    assert page.locator("#logo-preview").is_visible()
    page.locator('#appearance-form [type="submit"]').click()
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent.startsWith('Settings saved')"
    )
    page.reload()
    page.wait_for_function("() => !document.getElementById('appearance-fields').disabled")
    assert page.locator("#logo-preview").is_visible()
    saved_logo = page.locator("#logo-preview").get_attribute("src")
    page.locator("#settings-logo").set_input_files(
        {
            "name": "too-large.png",
            "mimeType": "image/png",
            "buffer": png.ljust(500 * 1024 + 1, b"\0"),
        }
    )
    assert "no larger than 500 KB" in page.locator("#settings-status").inner_text()
    assert page.locator("#logo-preview").get_attribute("src") == saved_logo
    assert page.locator("#settings-logo").evaluate("node => node.value === ''")
    page.locator("#remove-logo").click()
    page.locator('#appearance-form [type="submit"]').click()
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent.startsWith('Settings saved')"
    )


@pytest.mark.parametrize("mime_type", ["", "image/jpg"])
def test_logo_upload_detects_content_and_save_waits_for_file_read(live_page, mime_type):
    import io

    from PIL import Image

    page, url = live_page
    page.add_init_script("""(() => {
        const read = FileReader.prototype.readAsDataURL;
        FileReader.prototype.readAsDataURL = function(file) {
            setTimeout(() => read.call(this, file), 250);
        };
    })()""")
    page.goto(url + "/settings")
    page.wait_for_function("() => !document.getElementById('appearance-fields').disabled")
    output = io.BytesIO()
    Image.new("RGB", (32, 32), "blue").save(output, format="PNG")
    page.locator("#settings-logo").set_input_files(
        {"name": "logo.png", "mimeType": mime_type, "buffer": output.getvalue()}
    )
    page.evaluate("document.getElementById('appearance-form').requestSubmit()")
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent.startsWith('Settings saved')"
    )
    assert page.locator("#logo-preview").get_attribute("src").startswith("data:image/png;base64,")
    page.reload()
    page.wait_for_function("() => !document.getElementById('appearance-fields').disabled")
    assert page.locator("#logo-preview").is_visible()
    assert page.locator("#logo-preview").evaluate(
        "node => node.complete && node.naturalWidth === 32"
    )
    page.locator("#remove-logo").click()
    page.locator('#appearance-form [type="submit"]').click()
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent.startsWith('Settings saved')"
    )


def test_logo_save_shows_server_validation_reason_and_keeps_draft(live_page):
    import io

    from PIL import Image

    page, url = live_page
    page.goto(url + "/settings")
    page.wait_for_function("() => !document.getElementById('appearance-fields').disabled")
    output = io.BytesIO()
    Image.new("RGB", (32, 32)).save(output, format="PNG")
    page.locator("#settings-logo").set_input_files(
        {"name": "logo.png", "mimeType": "image/png", "buffer": output.getvalue()}
    )
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent.startsWith('Logo ready')"
    )
    logo = page.locator("#logo-preview").get_attribute("src")
    page.route(
        "**/api/admin/appearance",
        lambda route: route.fulfill(
            status=422,
            json={
                "detail": [
                    {
                        "loc": ["body", "logo"],
                        "msg": "Logo validation failed.",
                        "input": "raw-input-must-not-be-displayed",
                    }
                ]
            },
        ),
    )
    page.locator('#appearance-form [type="submit"]').click()
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent"
        ".includes('logo: Logo validation failed.')"
    )
    assert "raw-input-must-not-be-displayed" not in page.locator("#settings-status").inner_text()
    assert page.locator("#logo-preview").get_attribute("src") == logo
    assert page.locator("#appearance-fields").is_enabled()


def test_logo_dimension_error_explains_the_actual_image_size(live_page):
    import io

    from PIL import Image

    page, url = live_page
    page.goto(url + "/settings")
    page.wait_for_function("() => !document.getElementById('appearance-fields').disabled")
    output = io.BytesIO()
    Image.new("RGB", (2049, 1)).save(output, format="PNG")
    page.locator("#settings-logo").set_input_files(
        {"name": "wide-logo.png", "mimeType": "image/png", "buffer": output.getvalue()}
    )
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent.includes('2049 × 1')"
    )
    assert "2048 × 2048" in page.locator("#settings-status").inner_text()
    assert page.locator("#settings-logo").evaluate("node => node.value === ''")


@pytest.mark.parametrize("width", [1440, 390])
def test_settings_preview_isolation_overlay_and_save(live_page, width):
    page, url = live_page
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(url + "/settings")
    page.wait_for_function(
        "() => !document.getElementById('appearance-fields').disabled && "
        "document.getElementById('preview-loading').hidden"
    )
    shortcut = page.get_by_role("link", name="Settings", exact=True)
    assert shortcut.is_visible()
    assert shortcut.get_attribute("aria-current") == "page"
    assert page.locator('.primary-nav a[href="/settings"]').count() == 0
    assert shortcut.evaluate("node => node.nextElementSibling.classList.contains('profile-menu')")
    gear = shortcut.bounding_box()
    profile = page.locator("#profile-toggle").bounding_box()
    assert gear["x"] + gear["width"] <= profile["x"]
    assert abs((gear["y"] + gear["height"] / 2) - (profile["y"] + profile["height"] / 2)) < 2
    theme_toggle = page.locator("#floating-theme-toggle")
    assert theme_toggle.is_visible()
    initial_theme = page.locator("html").get_attribute("data-theme")
    theme_toggle.click()
    assert page.locator("html").get_attribute("data-theme") != initial_theme
    assert page.evaluate("localStorage.getItem('quality-lifecycle-studio-theme')") == (
        page.locator("html").get_attribute("data-theme")
    )
    position = theme_toggle.bounding_box()
    assert 0 <= width - position["x"] - position["width"] <= 30
    assert 0 <= 900 - position["y"] - position["height"] <= 30
    theme_toggle.click()
    assert page.locator("html").get_attribute("data-theme") == initial_theme
    assert page.frame_locator("#main-screen-preview").locator("#floating-theme-toggle").count() == 0
    original = page.locator(".brand strong").inner_text()
    title = "Workspace " + uuid4().hex[:8]
    page.locator('input[name="title"]').fill(title)
    page.wait_for_function(
        "() => document.getElementById('main-screen-preview').contentDocument"
        ".querySelector('.brand strong').textContent === "
        "document.querySelector('input[name=title]').value"
    )
    assert page.locator(".brand strong").inner_text() == original
    page.locator("#expand-preview").click()
    assert page.locator("#preview-dialog").evaluate("node => node.matches(':modal')")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.getElementById('preview-dialog').matches(':modal')")
    assert page.locator("#expand-preview").evaluate("node => node === document.activeElement")
    page.locator('#appearance-form [type="submit"]').click()
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent.startsWith('Settings saved')"
    )
    assert page.locator(".brand strong").inner_text() == title
    page.reload()
    page.wait_for_function("() => !document.getElementById('appearance-fields').disabled")
    assert page.locator('input[name="title"]').input_value() == title
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator("#reset-appearance").click()
    page.wait_for_function(
        "() => document.querySelector('.brand strong').textContent === 'Auto Finance Quality'"
    )


@pytest.mark.parametrize("width", [1440, 390])
def test_saved_identity_never_flashes_default_names_during_navigation(live_page, width):
    import io

    from PIL import Image

    page, url = live_page
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(url + "/settings")
    page.wait_for_function("() => !document.getElementById('appearance-fields').disabled")
    title = "Team Workspace " + uuid4().hex[:8]
    subtitle = "Application engineering"
    page.locator('input[name="title"]').fill(title)
    page.locator('input[name="subtitle"]').fill(subtitle)
    output = io.BytesIO()
    Image.new("RGB", (32, 32), "blue").save(output, format="PNG")
    page.locator("#settings-logo").set_input_files(
        {"name": "brand.png", "mimeType": "image/png", "buffer": output.getvalue()}
    )
    page.locator('#appearance-form [type="submit"]').click()
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent.startsWith('Settings saved')"
    )
    page.add_init_script("""(() => {
        window.identityFrames = [];
        function sample() {
            const brand = document.querySelector('.brand strong');
            const visible = brand && brand.getClientRects().length
                && getComputedStyle(brand).visibility !== 'hidden';
            if (window.identityFrames.length < 500)
                window.identityFrames.push({title: document.title,
                    brand: visible ? brand.textContent : null});
            requestAnimationFrame(sample);
        }
        requestAnimationFrame(sample);
    })()""")

    def slow_appearance(route):
        response = route.fetch()
        time.sleep(0.25)
        route.fulfill(response=response)

    page.route("**/api/appearance", slow_appearance)
    for path in (
        "/?view=stories",
        "/knowledge?view=overview",
        "/agent-information",
        "/documentation#knowledge-skills",
        "/settings",
    ):
        page.goto(url + path)
        page.wait_for_function(
            "() => !document.documentElement.hasAttribute('data-appearance-pending')"
        )
        page.evaluate(
            "() => new Promise(resolve => "
            "requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        assert page.locator(".brand strong").inner_text() == title
        assert page.locator(".brand small").inner_text() == subtitle
        assert page.locator(".brand-mark img").count() == 1
        assert page.title().endswith(title)
        frames = page.evaluate("identityFrames")
        assert any(frame["brand"] == title for frame in frames)
        assert all(frame["brand"] in (None, title) for frame in frames), frames
        assert all("Auto Finance Quality" not in frame["title"] for frame in frames), frames
    # Hash navigation and later page scripts must not restore a captured built-in title.
    page.goto(url + "/documentation#knowledge-skills")
    page.wait_for_function(
        "() => !document.documentElement.hasAttribute('data-appearance-pending')"
    )
    page.evaluate("location.hash = ''")
    page.wait_for_function("() => !document.body.hasAttribute('data-knowledge-guide')")
    assert page.title().endswith(title)
    page.goto(url + "/settings")
    page.wait_for_function("() => !document.getElementById('appearance-fields').disabled")
    page.locator("#reset-appearance").click()
    page.wait_for_function(
        "() => document.querySelector('.brand strong').textContent === 'Auto Finance Quality'"
    )


@pytest.mark.parametrize("width", [1440, 1100, 1024, 768, 390, 320])
@pytest.mark.parametrize("font_size", [16, 22])
def test_brand_geometry_stays_consistent_across_workspace_pages(live_page, width, font_size):
    import base64
    import io

    from PIL import Image

    from app.appearance import Appearance

    page, url = live_page
    ready_workspace_provider(page)
    output = io.BytesIO()
    Image.new("RGB", (1254, 1254), "teal").save(output, format="PNG")
    branding = Appearance(
        title="QualiForge AI",
        subtitle="Building software quality through intelligent agents",
        logo="data:image/png;base64," + base64.b64encode(output.getvalue()).decode(),
        font_size=font_size,
    ).model_dump(mode="json")
    page.route("**/api/appearance", lambda route: route.fulfill(json=branding))
    page.set_viewport_size({"width": width, "height": 900})
    reference = None
    for path in (
        "/",
        "/?view=stories",
        "/knowledge?view=overview",
        "/agent-information",
        "/knowledge-agents",
        "/documentation#knowledge-skills",
        "/logs",
        "/settings",
        "/admin/users",
        "/docs",
        "/user-guide",
    ):
        page.goto(url + path)
        page.wait_for_function(
            "() => !document.documentElement.hasAttribute('data-appearance-pending')"
        )
        page.evaluate("document.fonts.ready")
        boxes = page.locator(".sidebar-header").evaluate("""header => {
            const selectors = ['.brand', '.brand-mark', '.brand > span:last-child',
                '.brand strong', '.brand small', '.sidebar-toggle'];
            return Object.fromEntries(selectors.map(selector => {
                const node = header.querySelector(selector);
                const style = getComputedStyle(node);
                return [selector, {...node.getBoundingClientRect().toJSON(), font: style.fontSize}];
            }));
        }""")
        mark, copy = boxes[".brand-mark"], boxes[".brand > span:last-child"]
        title, tagline = boxes[".brand strong"], boxes[".brand small"]
        assert mark["width"] >= 32 and abs(mark["width"] - mark["height"]) < 1, (path, boxes)
        assert mark["right"] < copy["x"]
        assert copy["width"] > 0
        assert mark["x"] >= boxes[".brand"]["x"] - 1
        assert copy["right"] <= boxes[".brand"]["right"] + 1
        assert mark["right"] <= boxes[".sidebar-toggle"]["x"]
        assert page.locator(".brand strong").is_visible()
        assert page.locator(".brand small").is_visible()
        assert abs(title["x"] - tagline["x"]) < 1
        assert title["bottom"] < tagline["y"]
        assert boxes[".brand"]["right"] <= boxes[".sidebar-toggle"]["x"]
        geometry = [
            round(boxes[key][dimension], 2)
            for key in (".brand", ".brand-mark", ".brand strong", ".brand small")
            for dimension in ("width", "height")
        ]
        if reference is None:
            reference = geometry
        assert geometry == reference, (path, geometry, reference)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), path
    page.locator("#sidebar-toggle").click()
    if width > 1080:
        assert page.locator(".brand strong").is_hidden()
        collapsed = page.locator(".brand-mark").bounding_box()
        assert abs(collapsed["width"] - collapsed["height"]) < 1
        assert page.locator(".brand-mark").is_visible()
        page.locator("#sidebar-toggle").click()
        assert page.locator(".brand strong").is_visible()
    else:
        assert page.locator(".brand strong").is_visible()
        page.wait_for_function("""() =>
            document.getElementById('sidebar-content').getBoundingClientRect().top
            >= document.querySelector('.sidebar').getBoundingClientRect().bottom - 1
        """)


def test_appearance_load_failure_does_not_leave_navigation_hidden(live_page):
    page, url = live_page
    page.route(
        "**/api/appearance", lambda route: route.fulfill(status=503, json={"detail": "Unavailable"})
    )
    page.goto(url + "/knowledge?view=overview")
    page.wait_for_function(
        "() => !document.documentElement.hasAttribute('data-appearance-pending')"
    )
    assert page.locator(".brand").is_visible()
    assert page.locator(".primary-nav").is_visible()
    assert page.title() != "Loading workspace…"


def test_agent_directory_sections_search_and_custom_persistence(live_page):
    page, url = live_page
    page.goto(url + "/agent-information?view=all")
    page.wait_for_function(
        "() => document.getElementById('agent-list').getAttribute('aria-busy') === 'false'"
    )
    assert page.locator(".agent-category-section").count() == 6
    assert page.locator(".agent-category-section[open]").count() == 0
    page.locator("#expand-agent-sections").click()
    assert page.locator(".agent-category-section[open]").count() == 6
    page.locator("#collapse-agent-sections").click()
    page.locator("#agent-search").fill("no-such-agent-xyz")
    assert page.locator(".agent-directory-empty").is_visible()
    page.locator("#clear-agent-filters").click()
    page.locator("#open-custom-agent").click()
    page.locator("#custom-agent-name").fill("Browser specialist")
    page.locator("#custom-agent-purpose").fill("Review keyboard access and accessible names")
    page.locator("#custom-agent-instructions").fill(
        "Use approved requirements and record missing acceptance criteria."
    )
    page.locator('#custom-agent-form [type="submit"]').click()
    page.wait_for_function("() => !document.getElementById('custom-agent-dialog').open")
    page.reload()
    page.wait_for_function(
        "() => document.getElementById('agent-list').getAttribute('aria-busy') === 'false'"
    )
    assert page.locator("#custom-agent-count").inner_text() == "1"
    agents_nav = page.locator("#workspace-agents")
    assert agents_nav.locator("a > span:last-child").all_text_contents() == ["Agents"]
    assert agents_nav.locator(".nav-parent, .nav-children").count() == 0
    page.get_by_role("link", name="Agents", exact=True).click()
    page.wait_for_url(url + "/agent-information")
    page.wait_for_function(
        "() => document.getElementById('agent-list').getAttribute('aria-busy') === 'false'"
    )
    assert page.locator(".topbar h1").inner_text() == "Agents"
    assert page.locator('.agent-category-section[data-category="custom"]').count() == 0
    assert page.locator("#registered-agent-count").inner_text() == "22"
    page.goto(url + "/agent-information?view=custom")
    page.wait_for_function(
        "() => document.getElementById('agent-list').getAttribute('aria-busy') === 'false'"
    )
    assert page.locator(".topbar h1").inner_text() == "Custom agents"
    assert page.locator('.agent-category-section[data-category="custom"]').count() == 1
    assert page.locator('.agent-category-section[data-category="requirements"]').count() == 0
    assert (
        page.get_by_role("link", name="Agents", exact=True).get_attribute("aria-current") == "page"
    )


def test_knowledge_json_import_is_saved_only_as_a_draft(live_page, tmp_path):
    page, url = live_page
    page.goto(url + "/knowledge-agents")
    wait_ready(page)
    fixture = json.loads(
        (Path(__file__).parents[1] / "automation/Input/KnowledgeAgents.Json").read_text()
    )["reference-contributor"]
    fixture["name"] = "Imported contributor " + uuid4().hex[:8]
    source = tmp_path / "knowledge.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "agent": {"latest": {"status": "published", "revision": 99, "definition": fixture}},
            }
        )
    )
    before = page.locator(".ka-card").count()
    page.locator("#ka-import-file").set_input_files(source)
    page.wait_for_function("() => document.getElementById('ka-editor').open")
    assert page.locator('#ka-form [name="name"]').input_value() == fixture["name"]
    assert page.locator(".ka-card").count() == before
    page.locator('#ka-form [type="submit"]').click()
    page.wait_for_function("() => !document.getElementById('ka-editor').open")
    page.locator("#ka-search").fill(fixture["name"])
    assert page.locator(".ka-badge").inner_text() == "Not published"
    assert "v1 · draft" in page.locator(".ka-card").inner_text()


def test_settings_custom_domain_profile_selection(live_page):
    page, url = live_page
    page.goto(url + "/settings")
    page.wait_for_function("() => !document.getElementById('new-domain-profile').disabled")
    page.locator("#new-domain-profile").click()
    identifier = "ui-domain-" + uuid4().hex[:8]
    fields = {
        "id": identifier,
        "name": "Service quality domain",
        "description": "Use supplied service requirements across sectors.",
        "instructions": (
            "Use only supplied requirements and approved source evidence. "
            "Do not infer finance rules or unsupported domain constraints."
        ),
        "review_note": "Reviewed profile guidance and preserved source approval metadata.",
    }
    for name, value in fields.items():
        page.locator(f'#domain-profile-form [name="{name}"]').fill(value)
    page.locator('#domain-profile-form [name="confirmed"]').check()
    page.locator('#domain-profile-form [type="submit"]').click()
    page.wait_for_function("() => !document.getElementById('domain-profile-editor').open")
    assert page.locator("#domain-profile-choice").input_value() == identifier
    page.locator("#apply-domain-profile").click()
    page.wait_for_function(
        "() => document.getElementById('domain-profile-status').textContent"
        ".startsWith('Applied ui-domain-')"
    )
    page.goto(url + "/knowledge-agents")
    wait_ready(page)
    assert identifier in page.locator("#ka-status").inner_text()
    page.goto(url + "/settings")
    page.wait_for_function("() => !document.getElementById('domain-profile-choice').disabled")
    assert page.locator("#domain-profile-choice").input_value() == identifier
    page.locator("#domain-profile-choice").select_option("auto-finance-quotation")
    page.locator("#apply-domain-profile").click()
    page.wait_for_function(
        "() => document.getElementById('domain-profile-status').textContent"
        ".startsWith('Applied auto-finance-quotation')"
    )


def test_background_palette_contrast_and_reset(live_page):
    page, url = live_page
    page.goto(url + "/settings")
    page.wait_for_function(
        "() => !document.getElementById('appearance-fields').disabled && "
        "document.getElementById('preview-loading').hidden"
    )
    original = page.locator("html").get_attribute("data-background-tone")
    page.locator("#default-background").uncheck()

    def luminance(colour):
        channels = [int(colour[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
        return sum(v * weight for v, weight in zip(linear, [0.2126, 0.7152, 0.0722], strict=True))

    for colour in ["#ffffff", "#10121a", "#777777", "#0066cc", "#ffff00", "#ff0000", "#663399"]:
        page.locator('input[name="background"]').fill(colour)
        page.wait_for_function(
            "colour => document.getElementById('main-screen-preview').contentDocument"
            ".documentElement.style.getPropertyValue('--workspace-background') === colour",
            arg=colour,
        )
        palette = (
            page.frame_locator("#main-screen-preview")
            .locator("html")
            .evaluate(
                """node => {
                const style = getComputedStyle(node);
                const names = ['bg', 'surface', 'surface-soft', 'surface-tint',
                    'primary-soft', 'success-soft', 'warning-soft', 'danger-soft',
                    'ink', 'ink-soft', 'muted', 'primary', 'success', 'warning', 'danger',
                    'on-primary'];
                return Object.fromEntries(names.map(name =>
                    [name, style.getPropertyValue('--' + name).trim()]));
            }"""
            )
        )
        for text in ["ink", "ink-soft", "muted", "primary", "success", "warning", "danger"]:
            for surface in [
                "bg",
                "surface",
                "surface-soft",
                "surface-tint",
                "primary-soft",
                "success-soft",
                "warning-soft",
                "danger-soft",
            ]:
                light, dark = sorted(
                    [luminance(palette[text]), luminance(palette[surface])], reverse=True
                )
                assert (light + 0.05) / (dark + 0.05) >= 4.5, (colour, text, surface)
        light, dark = sorted(
            [luminance(palette["primary"]), luminance(palette["on-primary"])], reverse=True
        )
        assert (light + 0.05) / (dark + 0.05) >= 4.5
        assert page.locator("html").get_attribute("data-background-tone") == original
    page.locator('#appearance-form [type="submit"]').click()
    page.wait_for_function(
        "() => document.getElementById('settings-status').textContent.startsWith('Settings saved')"
    )
    assert page.locator("html").get_attribute("data-background-tone") == "dark"
    page.reload()
    page.wait_for_function("() => document.documentElement.dataset.backgroundTone === 'dark'")
    page.locator("#reset-appearance").click()
    page.wait_for_function("() => !document.documentElement.hasAttribute('data-custom-background')")
    assert page.locator("html").evaluate("node => node.style.getPropertyValue('--ink')") == ""
    assert page.locator("html").evaluate("node => node.style.colorScheme") == ""


@pytest.mark.parametrize("width", [1440, 390])
def test_workspace_navigation_sections_search_and_requirements_home(live_page, width):
    page, url = live_page
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(url + "/")
    page.wait_for_function("() => document.body.dataset.role === 'admin'")
    if width < 1081:
        page.locator("#sidebar-toggle").click()
    sidebar = page.locator(".sidebar")
    assert sidebar.locator(".primary-nav > .nav-label").inner_text() == "Workspace"
    assert sidebar.locator(
        ".workspace-nav-section > .nav-item > span:nth-child(2)"
    ).all_text_contents() == [
        "Agents",
        "Knowledge",
        "Quality Engineering",
        "Data",
        "Delivery & Operations",
        "AI Assure",
        "Administration",
    ]
    search = sidebar.get_by_role("searchbox", name="Search navigation")
    search.fill("business view")
    assert sidebar.locator(".workspace-nav-section:visible").count() == 1
    assert sidebar.get_by_role("link", name="Knowledge", exact=True).is_visible()
    search.fill("no-such-workspace-link")
    assert sidebar.locator(".workspace-nav-empty").is_visible()
    search.press("Escape")
    assert search.input_value() == ""
    assert sidebar.locator(".workspace-nav-section:visible").count() == 7
    search.fill("runtime logs")
    assert sidebar.get_by_role("button", name="Delivery & Operations").is_visible()
    sidebar.get_by_role("link", name="Runtime logs", exact=True).click()
    page.wait_for_url(url + "/logs")
    if width < 1081:
        page.locator("#sidebar-toggle").click()
    page.get_by_role("button", name="Quality Engineering", exact=True).click()
    page.get_by_role("link", name="Requirements", exact=True).click()
    page.wait_for_url(url + "/")
    assert page.locator(".topbar h1").inner_text() == "Requirements"
    assert page.locator("#description").is_visible()
    assert page.get_by_role("link", name="New Chat", exact=True).count() == 0
    assert page.locator('.primary-nav a[href="/project-dashboard"]').count() == 0
    assert page.locator("#settings-shortcut").is_visible()


@pytest.mark.parametrize("width", [1440, 1024, 768, 390, 320])
def test_knowledge_categories_and_source_views(live_page, width):
    page, url = live_page
    page.set_viewport_size({"width": width, "height": 1000})
    page.goto(url + "/knowledge?view=overview")
    board = page.locator("#knowledge-board")
    assert board.locator(".knowledge-board-column-heading h3").all_text_contents() == [
        "Product understanding",
        "Memory",
        "Agent behavior",
    ]
    assert board.locator(".knowledge-tool-card").count() == 9
    assert board.locator(".knowledge-tool-card .knowledge-tool-icon").count() == 9
    sidebar = page.locator("#knowledge-navigation")
    assert sidebar.locator(".nav-parent, .nav-children").count() == 0
    assert sidebar.locator("a").count() == 1
    assert sidebar.locator('a[aria-current="page"] > span:last-child').inner_text() == "Knowledge"
    if width > 1100:
        columns = board.locator(".knowledge-board-column").all()
        assert len({round(column.bounding_box()["x"]) for column in columns}) == 3
        assert len({round(column.bounding_box()["y"]) for column in columns}) == 1
    assert page.locator("#knowledge-board-filters").bounding_box()["y"] >= (
        page.locator("#knowledge-board-search").bounding_box()["y"]
        + page.locator("#knowledge-board-search").bounding_box()["height"]
    )
    page.get_by_role("button", name="Agent behavior", exact=True).click()
    assert board.locator(".knowledge-board-column").count() == 1
    assert board.locator(".knowledge-tool-card").count() == 3
    page.locator("#knowledge-board-search").fill("conventions")
    assert board.locator(".knowledge-tool-card").count() == 1
    assert board.get_by_role("link", name="Skills", exact=True).is_visible()
    page.locator("#knowledge-board-search").press("Escape")
    page.get_by_role("button", name="All tools", exact=True).click()
    assert board.locator(".knowledge-tool-card").count() == 9
    board.get_by_role("link", name="Services", exact=True).click()
    page.wait_for_url(url + "/documentation#knowledge-services")
    assert page.locator("#knowledge-services").is_visible()
    assert page.locator(".topbar h1").inner_text() == "Services"
    page.wait_for_function(
        "() => document.getElementById('knowledge-services').getBoundingClientRect().top > 0 && "
        "document.getElementById('knowledge-services').getBoundingClientRect().top < innerHeight"
    )
    assert page.get_by_role("link", name="← Knowledge", exact=True).is_visible()
    assert page.locator("#knowledge-navigation a").get_attribute("aria-current") == "page"
    if width < 1081:
        page.locator("#sidebar-toggle").click()
    page.locator("#knowledge-navigation a").click()
    page.wait_for_url(url + "/knowledge?view=overview")
    page.locator("#knowledge-board").get_by_role("link", name="Memory", exact=True).click()
    assert page.locator("h1").inner_text() == "Memory"
    assert "not configured" in page.locator(".page-intro").inner_text()
    assert page.locator('[data-knowledge-view="saved"]').first.is_visible()
    page.goto(url + "/knowledge?view=search")
    page.wait_for_function(
        "() => document.getElementById('knowledge-search-status').textContent"
        ".includes('matching records')"
    )
    assert "unavailable" not in page.locator("#knowledge-search-status").inner_text()
    query_box = page.locator("#knowledge-everything-search").bounding_box()
    filter_box = page.locator("#knowledge-source-filter").bounding_box()
    if width > 700:
        assert abs(query_box["y"] - filter_box["y"]) < 2
    else:
        assert abs(query_box["x"] - filter_box["x"]) < 2
        assert abs(query_box["width"] - filter_box["width"]) < 2
        assert query_box["y"] + query_box["height"] < filter_box["y"]
    page.locator("#knowledge-source-filter").select_option("standard")
    assert page.locator(".knowledge-search-card").count() == 2
    page.locator("#knowledge-everything-search").fill("no-matching-knowledge-record")
    assert page.locator(".knowledge-search-card").count() == 0
    assert "No matching knowledge" in page.locator("#knowledge-search-results").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 320])
@pytest.mark.parametrize(
    "fragment,title,catalog,count",
    [
        ("knowledge-skills", "Skills", "application-skill-catalog", 6),
        ("knowledge-guardrails", "Guardrails", "application-guardrail-catalog", 4),
    ],
)
def test_application_policy_catalogues_are_accessible(
    live_page, width, fragment, title, catalog, count
):
    page, url = live_page
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(url + "/documentation#" + fragment)
    assert page.locator(".topbar h1").inner_text() == title
    assert page.locator("#" + fragment).is_visible()
    assert page.locator(f"#{catalog} > div").count() == count
    assert page.get_by_role("link", name="← Knowledge", exact=True).is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=f"/tmp/{fragment}-{width}.png", full_page=True)


def ready_workspace_provider(page):
    page.route(
        "**/api/llm/models",
        lambda route: route.fulfill(
            json={
                "models": [
                    {
                        "model": "codex",
                        "display_name": "Codex CLI · GPT-6-ASTRA",
                        "can_use": True,
                        "reason": "Deterministic browser fixture",
                    }
                ]
            }
        ),
    )
    page.route(
        "**/api/llm/models/codex/access",
        lambda route: route.fulfill(
            json={
                "model": "codex",
                "display_name": "Codex CLI",
                "can_use": True,
                "reason": "Deterministic browser fixture",
                "status": "available",
            }
        ),
    )


@pytest.mark.parametrize("width", [1440, 768, 390, 320])
def test_login_lands_on_requirements(live_page, width):
    page, url = live_page
    ready_workspace_provider(page)
    page.context.clear_cookies()
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(url + "/login")
    page.locator("#username").fill("ui.admin")
    page.locator("#password").fill("Isolated-ui-password-123!")
    page.locator("#login-button").click()
    page.wait_for_url(url + "/")
    page.wait_for_function("() => document.body.dataset.role === 'admin'")
    assert page.locator(".topbar h1").inner_text() == "Requirements"
    assert page.locator("#stage-tab-1").get_attribute("aria-selected") == "true"
    assert page.locator("#description").is_visible()
    assert page.locator("#generate").is_disabled()
    assert page.locator(".workflow-navigation").is_visible()
    assert page.get_by_role("link", name="New Chat", exact=True).count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize("width", [1440, 390, 320])
@pytest.mark.parametrize("testing_type", ["api", "ui"])
def test_requirements_source_and_test_options_survive_navigation(live_page, width, testing_type):
    page, url = live_page
    ready_workspace_provider(page)
    generation_requests = []
    page.on(
        "request",
        lambda request: (
            generation_requests.append(request.url)
            if request.method == "POST" and "/api/workflow/" in request.url
            else None
        ),
    )
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(url + "/")
    page.wait_for_function("() => !document.getElementById('llm-model').disabled")
    page.locator("#add-requirement-source").click()
    with page.expect_file_chooser() as picker:
        page.locator("#upload-zone").click()
    picker.value.set_files(
        {"name": "context.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4 fixture"}
    )
    request_text = "Use the supplied application requirements and acceptance criteria for testing."
    page.locator("#description").fill(request_text)
    page.locator("#output-target").select_option("automation")
    page.locator("#manual-testing-type").select_option(testing_type)
    assert "context.pdf" in page.locator("#file-preview").inner_text()
    page.locator("#stage-tab-2").click()
    page.wait_for_url(url + "/?view=stories")
    page.locator("#stage-tab-1").click()
    page.wait_for_url(url + "/")
    assert page.locator("#description").input_value() == request_text
    assert page.evaluate("attachedFile.name") == "context.pdf"
    assert page.locator("#output-target").input_value() == "automation"
    assert page.locator("#manual-testing-type").input_value() == testing_type
    assert page.locator("#llm-model").input_value() == "codex"
    assert generation_requests == []
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_requirements_jira_import_and_story_generation(live_page):
    page, url = live_page
    ready_workspace_provider(page)
    handoff = json.loads(Path("automation/Input/Workflow.Json").read_text())["approved-scenarios"][
        "body"
    ]
    received = []

    def stories(route):
        received.append(route.request.post_data_json)
        route.fulfill(json=handoff["stories"])

    page.route("**/api/workflow/stories", stories)
    page.route(
        "**/api/jira/issues/TEST-123/requirements",
        lambda route: route.fulfill(
            json={
                "issue_key": "TEST-123",
                "summary": "Review supplied requirements",
                "description": handoff["request"]["description"],
                "acceptance_criteria": ["Use approved source evidence."],
            }
        ),
    )
    page.goto(url + "/")
    page.wait_for_function("() => !document.getElementById('llm-model').disabled")
    page.locator("#add-requirement-source").click()
    page.locator("#show-jira-link").click()
    page.locator("#jira-source-key").fill("https://jira.example/browse/TEST-123")
    page.locator("#load-jira").click()
    page.wait_for_function(
        "() => document.getElementById('description').value.includes('Jira story TEST-123')"
    )
    assert "Use approved source evidence." in page.locator("#description").input_value()
    assert received == []
    page.locator("#output-target").select_option("automation")
    page.locator("#manual-testing-type").select_option("api")
    page.locator("#generate").click()
    page.wait_for_url(url + "/?view=stories")
    assert len(received) == 1
    assert received[0]["llm_model"] == "codex"
    assert received[0]["generation_target"] == "automation"
    assert received[0]["manual_testing_type"] == "api"
    assert "Jira story TEST-123" in received[0]["description"]
    assert page.locator("#stage-panel-2").is_visible()


def test_requirements_test_choice_persists_on_reload(live_page):
    page, url = live_page
    ready_workspace_provider(page)
    request_text = "Create UI coverage for the application's sign-in and recovery journeys."
    page.locator("#description").fill(request_text)
    page.locator("#output-target").select_option("non_functional")
    page.locator("#output-target").select_option("automation")
    page.locator("#manual-testing-type").select_option("ui")
    page.wait_for_function("""() => {
        const draft = JSON.parse(sessionStorage.getItem('quality-workspace-draft:v1:ui.admin'));
        return draft?.controls['manual-testing-type'] === 'ui'
            && draft?.controls['output-target'] === 'automation';
    }""")
    page.reload()
    page.wait_for_function("() => document.getElementById('description').value.length > 0")
    assert page.url == url + "/"
    assert page.locator(".topbar h1").inner_text() == "Requirements"
    assert page.locator("#description").input_value() == request_text
    assert page.locator("#output-target").input_value() == "automation"
    assert page.locator("#manual-testing-type").input_value() == "ui"


def test_requirements_failed_jira_import_keeps_input(live_page):
    page, url = live_page
    page.route(
        "**/api/jira/issues/TEST-123/requirements",
        lambda route: route.fulfill(
            status=503, json={"detail": "Jira is temporarily unavailable."}
        ),
    )
    request_text = "Keep these original requirements while importing Jira context."
    page.locator("#description").fill(request_text)
    page.locator("#add-requirement-source").click()
    page.locator("#show-jira-link").click()
    page.locator("#jira-source-key").fill("TEST-123")
    page.locator("#load-jira").click()
    page.wait_for_function(
        "() => document.getElementById('status').textContent.includes('temporarily unavailable')"
    )
    assert page.url == url + "/"
    assert page.locator("#description").input_value() == request_text
    assert page.locator("#load-jira").is_enabled()


def test_requirements_review_failure_keeps_input_editable(live_page):
    page, url = live_page
    ready_workspace_provider(page)
    received = []

    def review(route):
        received.append(route.request.post_data_json)
        route.fulfill(status=503, json={"detail": "Review provider temporarily unavailable."})

    page.route("**/api/workflow/ba-review", review)
    page.goto(url + "/")
    page.wait_for_function("() => !document.getElementById('llm-model').disabled")
    page.locator("#description").fill(
        "Review supplied application requirements for missing acceptance criteria."
    )
    page.locator("#ba-review").click()
    page.wait_for_function(
        "() => document.getElementById('ba-status').textContent.includes('temporarily unavailable')"
    )
    assert len(received) == 1
    assert received[0]["llm_model"] == "codex"
    assert page.locator("#description").is_editable()
    assert page.url == url + "/"


def test_requirements_review_results_remain_scrollable(live_page):
    from test_business_analyst import assessment

    page, url = live_page
    ready_workspace_provider(page)
    report = assessment().model_dump(mode="json") | {
        "assessed_at": "2026-10-09T10:00:00Z",
        "document_fingerprint": "a" * 64,
        "knowledge_fingerprint": "b" * 64,
        "knowledge_sources": [],
        "knowledge_limitations": ["No effective approved business sources available."],
        "business_approval": "not_granted",
        "regulatory_compliance": "not_assessed",
        "domain_scope": {},
        "domain_validation": {
            "status": "needs_clarification",
            "alignment_percent": 66.7,
            "alignment_assessable": 3,
            "alignment_unassessable": 0,
            "topics_available": 3,
            "topics_reviewed": 3,
            "covered": 2,
            "gaps": 1,
            "conflicts": 0,
            "not_applicable": 0,
            "evidence_verified": True,
            "authority": "reference_only",
        },
    }
    page.route("**/api/workflow/ba-review", lambda route: route.fulfill(json=report))
    page.set_viewport_size({"width": 1280, "height": 720})
    page.goto(url + "/")
    page.wait_for_function("() => !document.getElementById('llm-model').disabled")
    page.locator("#description").fill("Quotation requests must reject a negative deposit.")
    page.locator("#ba-review").click()
    page.wait_for_function("() => !document.getElementById('ba-report').hidden")
    assert page.locator("#ba-report").is_visible()
    assert page.evaluate("document.documentElement.scrollHeight > innerHeight")
