import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.models import TestSuite as Suite
from app.services.stlc import LifecycleError, LifecycleStore
from app.stlc_models import (
    AttemptInput,
    BaselineInput,
    CycleInput,
    DefectInput,
    DefectUpdate,
    ImportInput,
    PackInput,
    RequirementInput,
    ReviewInput,
    SuiteVersionInput,
)


@pytest.fixture
def storage(tmp_path):
    return LifecycleStore(tmp_path / "memory.db")


def requirement(version=0, criteria=None):
    return RequirementInput(
        key="BR-001",
        title="Locked accounts",
        description="Reject locked accounts",
        owner="QA",
        source="PROJ-1",
        acceptance_criteria=criteria
        if criteria is not None
        else ["Locked accounts receive HTTP 403"],
        expected_version=version,
        change_reason="Review update",
    )


def approve(storage, kind, item):
    storage.review(
        kind, item["id"], ReviewInput(action="submit", comment="Ready for review"), "author"
    )
    return storage.review(
        kind,
        item["id"],
        ReviewInput(action="approve", comment="Reviewed acceptance criteria and coverage"),
        "reviewer",
    )


def prepared(storage):
    req = approve(storage, "requirement", storage.requirement(requirement(), "author"))
    baseline = approve(
        storage,
        "baseline",
        storage.baseline(BaselineInput(name="Release 1", requirement_ids=[req["id"]]), "author"),
    )
    suite = Suite(
        feature_name="Access",
        test_cases=[
            dict(
                id="TC-001",
                title="Locked account rejected",
                objective="Verify access denied",
                category="smoke",
                priority="P0",
                execution_mode="automation",
                feasibility_reason="HTTP status is observable",
                steps=[dict(action="Send locked credentials", expected_result="HTTP 403")],
                acceptance_criteria_covered=["BR-001"],
            )
        ],
    )
    snapshot = approve(
        storage,
        "suite",
        storage.suite(
            SuiteVersionInput(
                baseline_id=baseline["id"], suite=suite, mappings={"TC-001": ["BR-001"]}
            ),
            "author",
        ),
    )
    cycle = storage.cycle(
        CycleInput(
            suite_id=snapshot["id"],
            name="Regression",
            build="sha-1",
            environment="QA",
            assignments={"TC-001": "tester"},
        ),
        "author",
    )
    return req, baseline, snapshot, cycle


def test_version_change_preserves_baseline_results_and_blocks_new_cycle(storage):
    req, baseline, snapshot, cycle = prepared(storage)
    storage.import_results(
        cycle["id"],
        ImportInput(
            run_key="run-1",
            build="sha-1",
            environment="QA",
            results=[AttemptInput(case_id="TC-001", status="passed", actual="403")],
        ),
        "ci",
    )
    changed = storage.requirement(requirement(1, ["Locked accounts receive HTTP 423"]), "author")
    data = LifecycleStore(storage.path.parent / "memory.db").snapshot()
    assert data["baselines"][0]["requirements"][0]["acceptance_criteria"] == [
        "Locked accounts receive HTTP 403"
    ]
    assert data["impacts"][0]["case_ids"] == ["TC-001"]
    assert data["impacts"][0]["changed_fields"] == ["acceptance_criteria"]
    assert storage.report(cycle["id"])["matrix"][0]["passed"] is True
    with pytest.raises(LifecycleError, match="changed or unapproved"):
        storage.cycle(
            CycleInput(
                suite_id=snapshot["id"],
                name="New",
                build="sha-2",
                environment="QA",
                assignments={"TC-001": "tester"},
            ),
            "author",
        )
    approve(storage, "requirement", changed)
    assert storage.snapshot()["requirements"][0]["status"] == "superseded"


def test_review_quality_and_concurrent_edit_guards(storage):
    req = storage.requirement(requirement(criteria=[]), "author")
    with pytest.raises(LifecycleError, match="Invalid review"):
        storage.review(
            "requirement", req["id"], ReviewInput(action="approve", comment="OK"), "reviewer"
        )
    with pytest.raises(LifecycleError, match="quality flags"):
        approve(storage, "requirement", req)
    with pytest.raises(LifecycleError, match="reload"):
        storage.requirement(requirement(), "author")
    next_version = storage.requirement(requirement(1), "author")
    assert next_version["version"] == 2
    assert storage.snapshot()["audit"][0]["actor"] == "author"


def test_import_atomic_idempotent_and_build_bound(storage):
    *_, cycle = prepared(storage)
    body = ImportInput(
        run_key="run-1",
        build="sha-1",
        environment="QA",
        results=[AttemptInput(case_id="TC-001", status="failed", actual="HTTP 200")],
    )
    with pytest.raises(LifecycleError, match="build and environment"):
        storage.import_results(cycle["id"], body.model_copy(update={"build": "sha-2"}), "ci")
    invalid = body.model_copy(
        update={
            "results": body.results
            + [AttemptInput(case_id="UNKNOWN", status="passed", actual="OK")]
        }
    )
    with pytest.raises(LifecycleError, match="does not belong"):
        storage.import_results(cycle["id"], invalid, "ci")
    assert storage.snapshot()["attempts"] == []
    first = storage.import_results(cycle["id"], body, "ci")
    assert storage.import_results(cycle["id"], body, "ci") == first
    assert len(storage.snapshot()["attempts"]) == 1
    with pytest.raises(LifecycleError, match="different results"):
        storage.import_results(
            cycle["id"],
            body.model_copy(
                update={"results": [AttemptInput(case_id="TC-001", status="passed", actual="403")]}
            ),
            "ci",
        )


def test_manual_steps_defects_and_retest_history(storage):
    *_, cycle = prepared(storage)
    with pytest.raises(LifecycleError, match="each step"):
        storage.record_attempt(
            cycle["id"], AttemptInput(case_id="TC-001", status="passed", actual="403"), "tester"
        )
    failed = storage.record_attempt(
        cycle["id"],
        AttemptInput(
            case_id="TC-001",
            status="failed",
            actual="200",
            steps=[dict(step=1, status="failed", actual="200")],
        ),
        "tester",
    )
    defect = storage.defect(
        DefectInput(attempt_id=failed["id"], title="Locked account accepted", severity="critical"),
        "tester",
    )
    update = DefectUpdate(status="closed", comment="Retested")
    with pytest.raises(LifecycleError, match="passing retest"):
        storage.update_defect(defect["id"], update, "tester")
    storage.record_attempt(
        cycle["id"],
        AttemptInput(
            case_id="TC-001",
            status="passed",
            actual="403",
            retest_of=failed["id"],
            steps=[dict(step=1, status="passed", actual="403")],
        ),
        "tester",
    )
    storage.update_defect(defect["id"], update, "tester")
    report = storage.report(cycle["id"])
    assert len(report["attempts"]) == 2
    assert report["counts"]["passed"] == 1
    assert report["pass_rate"] == 100
    assert report["defects"][0]["status"] == "closed"


def test_no_execution_is_unavailable_and_mappings_reject_unknown(storage):
    _, baseline, snapshot, cycle = prepared(storage)
    assert storage.report(cycle["id"])["pass_rate"] is None
    assert storage.report(cycle["id"])["counts"]["not-run"] == 1
    with pytest.raises(LifecycleError, match="Map every"):
        storage.suite(
            SuiteVersionInput(
                baseline_id=baseline["id"],
                suite=Suite.model_validate(snapshot["suite"]),
                mappings={"TC-001": ["BR-unknown"]},
            ),
            "author",
        )


def runner():
    spec = importlib.util.spec_from_file_location(
        "stlc_runner", Path(__file__).parents[1] / "tools/run_stlc_bundle.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pack_manifest_and_trx_mapping(storage, tmp_path):
    *_, cycle = prepared(storage)
    payload = PackInput(
        files={"Tests.csproj": "<Project/>"},
        project_path="Tests.csproj",
        test_mappings={"LockedAccount": "TC-001"},
        review_comment="Reviewed source",
    )
    content = storage.pack(cycle["id"], payload, "reviewer")
    archive = tmp_path / "pack.zip"
    archive.write_bytes(content)
    manifest = runner().unpack(archive, tmp_path / "unpacked")
    assert manifest["reviewed_by"] == "reviewer"
    trx = tmp_path / "results.trx"
    trx.write_text(
        "<TestRun><Results>"
        '<UnitTestResult testName="LockedAccount" outcome="Passed"/></Results></TestRun>'
    )
    result = runner().convert_results(trx, manifest, "run-1")
    assert result["results"][0]["case_id"] == "TC-001"
    trx.write_text(
        "<TestRun><Results>"
        '<UnitTestResult testName="Unknown" outcome="Passed"/></Results></TestRun>'
    )
    with pytest.raises(ValueError, match="Unmapped"):
        runner().convert_results(trx, manifest, "run-1")
    with pytest.raises(LifecycleError, match="Unsafe"):
        storage.pack(
            cycle["id"], payload.model_copy(update={"files": {"../bad.csproj": "x"}}), "reviewer"
        )
    with zipfile.ZipFile(io.BytesIO(content)) as zipped:
        assert json.loads(zipped.read("manifest.json"))["cycle_id"] == cycle["id"]


def test_trx_requires_every_outline_row_before_aggregating(tmp_path):
    manifest = {
        "cycle_id": "cycle-1",
        "build": "build-1",
        "environment": "test",
        "test_mappings": {"RowOne": "TC-001", "RowTwo": "TC-001"},
    }
    trx = tmp_path / "results.trx"
    first = '<UnitTestResult testName="RowOne" outcome="Passed"/>'
    trx.write_text(f"<TestRun><Results>{first}</Results></TestRun>")
    with pytest.raises(ValueError, match="missing"):
        runner().convert_results(trx, manifest, "run-1")
    for outcome, expected in [
        ("Passed", "passed"),
        ("Failed", "failed"),
        ("NotExecuted", "not-run"),
    ]:
        second = f'<UnitTestResult testName="RowTwo" outcome="{outcome}"/>'
        trx.write_text(f"<TestRun><Results>{first}{second}</Results></TestRun>")
        converted = runner().convert_results(trx, manifest, "run-1")
        assert converted["results"][0]["status"] == expected


def test_ci_runner_writes_evidence_under_framework_reports(storage, tmp_path, monkeypatch):
    from types import SimpleNamespace

    *_, cycle = prepared(storage)
    bundles = tmp_path / "automation-packs"
    bundles.mkdir()
    (bundles / f"{cycle['id']}.zip").write_bytes(
        storage.pack(
            cycle["id"],
            PackInput(
                files={"Tests.csproj": "<Project/>", "TestResults/Reports/README.md": "Reports"},
                project_path="Tests.csproj",
                test_mappings={"LockedAccount": "TC-001"},
                review_comment="Reviewed source",
            ),
            "reviewer",
        )
    )
    module = runner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module.sys, "argv", ["run_stlc_bundle.py", cycle["id"]])

    def execute(command, **kwargs):
        if command[1] == "test":
            reports = Path(command[command.index("--results-directory") + 1])
            assert reports == tmp_path / "stlc-run/TestResults/Reports/ci-execution"
            (reports / "results.trx").write_text(
                '<TestRun><Results><UnitTestResult testName="LockedAccount" '
                'outcome="Passed"/></Results></TestRun>'
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", execute)
    assert module.main() == 0
    results = json.loads(
        (tmp_path / "stlc-run/TestResults/Reports/ci-execution/results.json").read_text()
    )
    assert results["cycle_id"] == cycle["id"]
    assert results["results"][0]["status"] == "passed"


def test_stlc_routes_persist_and_translate_conflicts(tmp_path):
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            response = client.post("/api/stlc/requirements", json=requirement().model_dump())
            assert response.status_code == 201, response.text
            assert (
                client.post("/api/stlc/requirements", json=requirement().model_dump()).status_code
                == 409
            )
            assert len(client.get("/api/stlc").json()["requirements"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_retest_on_new_build_preserves_original_cycle(storage):
    *_, snapshot, cycle = prepared(storage)
    failed = storage.record_attempt(
        cycle["id"],
        AttemptInput(
            case_id="TC-001",
            status="failed",
            actual="200",
            steps=[dict(step=1, status="failed", actual="200")],
        ),
        "tester",
    )
    defect = storage.defect(
        DefectInput(attempt_id=failed["id"], title="Wrong status", severity="major"), "tester"
    )
    new_cycle = storage.cycle(
        CycleInput(
            suite_id=snapshot["id"],
            name="Retest",
            build="sha-2",
            environment="QA",
            assignments={"TC-001": "tester"},
        ),
        "tester",
    )
    storage.record_attempt(
        new_cycle["id"],
        AttemptInput(
            case_id="TC-001",
            status="passed",
            actual="403",
            retest_of=failed["id"],
            steps=[dict(step=1, status="passed", actual="403")],
        ),
        "tester",
    )
    storage.update_defect(
        defect["id"], DefectUpdate(status="closed", comment="Confirmed in sha-2"), "tester"
    )
    assert storage.report(cycle["id"])["counts"]["failed"] == 1
    assert storage.report(new_cycle["id"])["counts"]["passed"] == 1


@pytest.mark.skipif(
    __import__("os").environ.get("RUN_BROWSER_TESTS") != "1", reason="Opt-in browser check"
)
def test_browser_records_manual_execution_and_reloads_evidence(tmp_path):
    import mimetypes
    from urllib.parse import urlparse

    pw = pytest.importorskip("playwright.sync_api")
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    storage = LifecycleStore(settings.organizational_memory_path)
    *_, cycle = prepared(storage)
    static = Path(__file__).parents[1] / "app/static"
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client, pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                path = urlparse(route.request.url).path
                if path in {"/", "/quality-lifecycle"} or path.startswith("/static/"):
                    file = static / (
                        "index.html"
                        if not path.startswith("/static/")
                        else path.removeprefix("/static/")
                    )
                    route.fulfill(
                        body=file.read_bytes(), content_type=mimetypes.guess_type(file)[0]
                    )
                elif path.startswith("/api/stlc"):
                    response = client.request(
                        route.request.method,
                        path,
                        content=route.request.post_data,
                        headers={"Content-Type": "application/json"},
                    )
                    route.fulfill(
                        status=response.status_code,
                        body=response.content,
                        content_type="application/json",
                    )
                elif path == "/api/workspace/rules":
                    route.fulfill(json={"business_rules": []})
                elif path == "/api/automation/history":
                    route.fulfill(json={"history": [], "active": [], "scope": "Repository BDD"})
                else:
                    route.fulfill(json={"ok": True, "models": [], "events": [], "complete": True})

            page.route("**/*", handle)
            page.goto("http://localhost/quality-lifecycle")
            page.locator("#stlc-workspace > details").nth(2).locator("summary").first.click()
            page.locator("#stlc-active-cycle").select_option(cycle["id"])
            page.locator("#stlc-attempt-case").select_option("TC-001")
            page.locator("[data-step-actual]").fill("HTTP 403 observed")
            page.locator('#stlc-attempt-form textarea[name="actual"]').fill(
                "Locked account rejected"
            )
            page.locator('#stlc-attempt-form button[type="submit"]').click()
            pw.expect(page.locator("#stlc-status")).to_contain_text("Saved.")
            pw.expect(page.locator("#stlc-cycle-report")).to_contain_text("All linked cases passed")
            page.reload()
            page.locator("#stlc-workspace > details").nth(2).locator("summary").first.click()
            page.locator("#stlc-active-cycle").select_option(cycle["id"])
            pw.expect(page.locator("#stlc-cycle-report")).to_contain_text("Locked account rejected")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors
            browser.close()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_jira_publication_and_sync_preserve_local_disposition(storage, monkeypatch):
    import httpx

    from app import stlc_routes
    from app.stlc_models import JiraDefectInput

    *_, cycle = prepared(storage)
    failed = storage.record_attempt(
        cycle["id"],
        AttemptInput(
            case_id="TC-001",
            status="failed",
            actual="200",
            steps=[dict(step=1, status="failed", actual="200")],
        ),
        "tester",
    )
    defect = storage.defect(
        DefectInput(attempt_id=failed["id"], title="Wrong status", severity="major"), "tester"
    )
    calls = []

    def transport(request):
        calls.append(request)
        if request.method == "POST":
            assert json.loads(request.content)["fields"]["project"]["key"] == "QA"
            return httpx.Response(201, json={"key": "QA-123"})
        return httpx.Response(200, json={"fields": {"status": {"name": "Done"}}})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        stlc_routes.httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(transport), **kwargs),
    )
    settings = Settings(
        _env_file=None,
        jira_base_url="https://jira.example",
        jira_email="qa@example.com",
        jira_api_token="test-only",
    )
    published = await stlc_routes.publish_defect(
        defect["id"], JiraDefectInput(project_key="QA"), storage, "reviewer", settings
    )
    assert published["jira_key"] == "QA-123"
    with pytest.raises(LifecycleError, match="linked"):
        await stlc_routes.publish_defect(
            defect["id"], JiraDefectInput(project_key="QA"), storage, "reviewer", settings
        )
    synced = await stlc_routes.sync_defect(defect["id"], storage, "reviewer", settings)
    assert synced["jira_status"] == "Done"
    assert synced["status"] == "open"
    assert len(calls) == 2
