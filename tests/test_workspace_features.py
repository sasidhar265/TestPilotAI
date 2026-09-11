import ast
import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.agents.context_converter_agent import ContextConverterAgent
from app.agents.lifecycle_agents import BusinessRulesAgent
from app.agents.multilanguage_agent import (
    LANGUAGES,
    ArtifactFile,
    LanguageArtifact,
    LanguageRequest,
    MultiLanguageAgent,
    safe_files,
    validate_pack,
)
from app.agents.test_case_validator import ValidationReport
from app.config import Settings, get_settings
from app.main import app
from app.memory import OrganizationalMemory
from app.models import BusinessRule, GenerateRequest
from app.models import TestSuite as Suite
from app.services.dashboard import DashboardStore, suite_details
from app.workspace_policy import load_business_rules, save_business_rules, without_tags


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    from app import workspace_policy

    monkeypatch.setattr(workspace_policy, "WORKSPACE", tmp_path)
    (tmp_path / "business-rules.json").write_text("[]")
    (tmp_path / "feature-standards.md").write_text("No feature tags")
    (tmp_path / "automation-standards.md").write_text("Use scenario-scoped state")
    return tmp_path


@pytest.fixture
def request_model():
    suite = Suite.model_validate(
        {
            "feature_name": "API responses",
            "test_cases": [
                {
                    "id": "TC-001",
                    "title": "Response status",
                    "objective": "Check status",
                    "category": "smoke",
                    "priority": "P1",
                    "execution_mode": "automation",
                    "feasibility_reason": "Stable API",
                    "steps": [{"action": "Send", "expected_result": "OK"}],
                    "gherkin": "@smoke\nScenario Outline: Response\n"
                    ' Given a request named "<name>"\n'
                    ' When I submit "POST" to "/quotes"\n Then status is 201\n'
                    "@data\n Examples:\n | name |\n | valid |",
                }
            ],
        }
    )
    return LanguageRequest(
        suite=suite,
        language="python",
        validation=ValidationReport(
            passed=True, score=100, acceptance_criteria_total=0, acceptance_criteria_covered=0
        ),
    )


def test_shared_rules_reload_and_reject_conflicts(workspace):
    request = GenerateRequest(description="Check the approved account behavior")
    save_business_rules([BusinessRule(id="BR-001", description="Reject locked accounts")])
    enriched = BusinessRulesAgent().enrich(request)
    assert "Reject locked accounts" in enriched.additional_context
    assert enriched.business_rules == load_business_rules()
    save_business_rules([BusinessRule(id="BR-001", description="Reject disabled accounts")])
    assert "Reject disabled accounts" in BusinessRulesAgent().enrich(request).additional_context
    with pytest.raises(ValueError, match="conflicts"):
        BusinessRulesAgent().enrich(enriched)
    with pytest.raises(ValueError, match="unique"):
        save_business_rules(load_business_rules() * 2)
    assert len(load_business_rules()) == 1


def test_standards_invalidate_suite_cache_without_discarding_reviews(workspace):
    request = GenerateRequest(description="Check the approved account behavior")
    before = OrganizationalMemory.key_for(request)
    review = OrganizationalMemory.review_key_for(request)
    (workspace / "feature-standards.md").write_text("New feature standards")
    assert OrganizationalMemory.key_for(request) != before
    assert OrganizationalMemory.review_key_for(request) == review


def test_tags_removed_without_changing_outline_or_payload(request_model):
    feature = ContextConverterAgent()._feature(request_model.suite).decode()
    assert "@smoke" not in feature and "@data" not in feature
    assert "Scenario Outline:" in feature and "| valid |" in feature
    payload = 'Given a document\n """\n @payload\n """\n @tag'
    assert "@payload" in without_tags(payload)
    assert "@tag" not in without_tags(payload)


@pytest.mark.parametrize("language", LANGUAGES)
def test_language_bindings_have_correct_framework_extension_and_coverage(request_model, language):
    request = request_model.model_copy(update={"language": language})
    artifact = MultiLanguageAgent(Settings(_env_file=None)).bindings(request)
    assert artifact.framework == LANGUAGES[language][1]
    assert artifact.files[0].path.endswith("." + LANGUAGES[language][2])
    assert len(artifact.coverage) == 3
    assert all(c.status == "blocked" for c in artifact.coverage)
    if language == "python":
        ast.parse(artifact.files[0].content)
        assert "(?P<arg1>" in artifact.files[0].content
        assert "(?P<arg2>" in artifact.files[0].content


def test_language_rejects_failed_gate_and_unknown_language(request_model):
    agent = MultiLanguageAgent(Settings(_env_file=None))
    with pytest.raises(ValueError, match="approved"):
        agent.bindings(
            request_model.model_copy(
                update={"validation": request_model.validation.model_copy(update={"passed": False})}
            )
        )
    with pytest.raises(ValueError):
        LanguageRequest.model_validate(request_model.model_dump() | {"language": "shell"})


@pytest.mark.parametrize(
    "path", ["../steps.py", "/steps.py", "a//steps.py", "steps.exe", "a\\b.py"]
)
def test_artifact_paths_fail_closed(path):
    artifact = LanguageArtifact(
        language="python", framework="Behave", files=[ArtifactFile(path=path, content="source")]
    )
    with pytest.raises(ValueError):
        safe_files(artifact)


def test_full_pack_rejects_pending_and_missing_coverage(request_model):
    baseline = MultiLanguageAgent(Settings(_env_file=None)).bindings(request_model)
    with pytest.raises(ValueError, match="concrete"):
        validate_pack(baseline, request_model, baseline)
    baseline.files[0].content = "assert True"
    with pytest.raises(ValueError, match="map every"):
        validate_pack(baseline, request_model, baseline)


@pytest.mark.asyncio
async def test_pack_uses_configured_runner_and_shared_standards(
    workspace, request_model, monkeypatch
):
    from app.agents.multilanguage_agent import ArtifactGenerationRunner

    runner = AsyncMock()
    monkeypatch.setattr(ArtifactGenerationRunner, "generate_structured", runner)
    await MultiLanguageAgent(Settings(_env_file=None)).generate(request_model)
    options = runner.call_args.kwargs
    assert "Use scenario-scoped state" in options["instructions"]
    assert "No feature tags" in options["instructions"]
    assert json.loads(options["prompt"])["language"] == "python"
    assert callable(options["validate"])


def test_dashboard_persists_real_counts_and_separates_repository_execution(tmp_path, request_model):
    store = DashboardStore(tmp_path / "memory.db")
    identifier = store.start("test_generation")
    assert store.snapshot()["active"][0]["status"] == "running"
    store.finish(identifier, "completed", suite_details(request_model.suite, True))
    repository = store.start("repository_checks")
    store.finish(repository, "passed", {"passed": 6, "failed": 0, "output": "Run complete"})
    snapshot = DashboardStore(tmp_path / "memory.db").snapshot()
    assert not snapshot["active"]
    assert snapshot["history"][0]["details"]["output"] == "Run complete"
    assert snapshot["history"][0]["finished_at"] >= snapshot["history"][0]["started_at"]
    assert snapshot["history"][0]["duration_ms"] >= 0
    assert snapshot["history"][0]["details"]["passed"] == 6
    assert snapshot["history"][1]["details"]["cases"][0]["execution"] == "not_run"


def test_workspace_routes_roundtrip_rules_and_language_files(workspace, request_model):
    settings = Settings(_env_file=None, organizational_memory_path=workspace / "memory.db")
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/workspace/rules",
                json={
                    "business_rules": [{"id": "BR-001", "description": "Reject locked accounts"}]
                },
            )
            assert response.status_code == 200
            assert client.get("/api/workspace/rules").json() == response.json()
            artifact = client.post(
                "/api/step-definitions/languages/bindings",
                json=request_model.model_dump(mode="json"),
            )
            assert artifact.status_code == 200
            assert artifact.json()["language"] == "python"
            archive = client.post("/api/step-definitions/languages/download", json=artifact.json())
            assert archive.status_code == 200
            assert archive.content.startswith(b"PK")
            assert client.get("/api/dashboard").status_code == 200
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_complete_python_pack_and_registration_validation(request_model):
    baseline = MultiLanguageAgent(Settings(_env_file=None)).bindings(request_model)
    artifact = baseline.model_copy(deep=True)
    artifact.files[0].content = artifact.files[0].content.replace(
        'raise NotImplementedError("Implement this step")', "assert context.response is not None"
    )
    artifact.files.extend(
        [
            ArtifactFile(path="requirements.txt", content="behave\n"),
            ArtifactFile(path="README.md", content="Install requirements and run behave."),
            ArtifactFile(
                path="Hooks/Hooks.py",
                content="def before_scenario(context, scenario):\n    context.response = None\n",
            ),
            ArtifactFile(
                path="TestContext/testcontext.py",
                content="class TestContext:\n    response = None\n",
            ),
        ]
    )
    for mapping in artifact.coverage:
        mapping.status = "generated"
    validated = validate_pack(artifact, request_model, baseline)
    feature = next(f for f in validated.files if f.path == "Features/generated.feature")
    assert "@smoke" not in feature.content
    validated.files[0].content = validated.files[0].content.replace("@given", "#@given")
    # Comments must not count as registered Python steps.
    validated.files[0].content = "\n".join(
        line for line in validated.files[0].content.splitlines() if not line.startswith("#@")
    )
    with pytest.raises(ValueError, match="registrations"):
        validate_pack(validated, request_model, baseline)


@pytest.mark.skipif(
    __import__("os").environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check"
)
def test_browser_shared_rules_language_selection_and_dashboard(workspace, request_model):
    import mimetypes
    from urllib.parse import urlparse

    playwright = pytest.importorskip("playwright.sync_api")
    static = __import__("pathlib").Path(__file__).parents[1] / "app/static"
    selected = []
    errors = []
    store = DashboardStore(workspace / "memory.db")
    store.finish(
        store.start("test_generation"), "completed", suite_details(request_model.suite, True)
    )
    save_business_rules([BusinessRule(id="BR-001", description="Reject locked accounts")])

    def handle(route):
        path = urlparse(route.request.url).path
        if path == "/" or path.startswith("/static/"):
            file = static / ("index.html" if path == "/" else path.removeprefix("/static/"))
            route.fulfill(body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0])
        elif path == "/api/workspace/rules":
            if route.request.method == "PUT":
                rules = [BusinessRule(**r) for r in route.request.post_data_json["business_rules"]]
                save_business_rules(rules)
            route.fulfill(json={"business_rules": [r.model_dump() for r in load_business_rules()]})
        elif path == "/api/workspace/standards":
            route.fulfill(json={"automation": "Use shared standards", "feature": "No tags"})
        elif path == "/api/automation/history":
            route.fulfill(json=store.snapshot("repository_checks"))
        elif path == "/api/step-definitions/languages/bindings":
            request = LanguageRequest.model_validate(route.request.post_data_json)
            selected.append(request.language)
            artifact = MultiLanguageAgent(Settings(_env_file=None)).bindings(request)
            route.fulfill(json=artifact.model_dump())
        elif path == "/api/automation/run":
            route.fulfill(
                json={
                    "status": "passed",
                    "passed": 6,
                    "failed": 0,
                    "skipped": 0,
                    "duration_ms": 1,
                    "output": "Repository checks only",
                }
            )
        else:
            route.fulfill(json={"ok": True, "models": [], "events": [], "complete": True})

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", handle)
        page.goto("http://localhost/")
        playwright.expect(page.locator("#business-rules")).to_have_value(
            "BR-001: Reject locked accounts"
        )
        page.locator("#rule-control summary").click()
        page.locator("#business-rules").fill("BR-002: Reject disabled accounts")
        page.locator("#save-business-rules").click()
        playwright.expect(page.locator("#rule-save-state")).to_have_text("Saved 1 shared rules")
        assert load_business_rules()[0].id == "BR-002"
        page.evaluate(
            """data => {
            startLifecycleFeed=()=>{};stopLifecycleFeed=async()=>{};
            validationReport=data.validation;render(data.suite);
        }""",
            request_model.model_dump(mode="json"),
        )
        for language in LANGUAGES:
            page.locator("#automation-language").select_option(language)
            page.locator("#suite-view-menu summary").click()
            page.locator("#generate-step-definitions").click()
            playwright.expect(page.locator("#step-definitions")).to_be_visible()
            playwright.expect(page.locator("#step-definition-files strong").first).to_contain_text(
                "." + LANGUAGES[language][2]
            )
        assert selected == list(LANGUAGES)
        page.locator('.primary-nav a[href="/quality-lifecycle"]').click()
        playwright.expect(page.locator("#metrics-dashboard")).to_contain_text(
            "Requirement-to-test traceability"
        )
        playwright.expect(page.locator("#metrics-dashboard")).to_contain_text(
            "Source rule inventory unavailable"
        )
        assert page.locator("#generate-data, #run-automation").count() == 0
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.locator('.primary-nav a[href="/progress"]').click()
        page.locator("#run-repository-bdd").click()
        playwright.expect(page.locator("#bdd-run-status")).to_contain_text("BDD execution passed")
        assert page.evaluate("executionSummary") is None
        page.locator("#refresh-dashboard").click()
        playwright.expect(page.locator("#bdd-result-summary")).to_contain_text(
            "No completed BDD runs"
        )
        page.screenshot(path="/tmp/workspace-dashboard-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path="/tmp/workspace-dashboard-mobile.png", full_page=True)
        assert not errors
        browser.close()
