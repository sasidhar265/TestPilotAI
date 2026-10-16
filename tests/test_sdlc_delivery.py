"""Coordinator/tool invariants with simulated specialists; never claims a production deployment."""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from app.agents.sdlc_agent import StageBlocked
from app.config import Settings
from app.sdlc_models import AgentDocument, DeliveryMission, SourceFile
from app.services.sdlc import SDLCError, SDLCStore
from app.services.sdlc_delivery import DeliveryCoordinator
from app.services.sdlc_tools import DeliveryTools, safe_path


def settings(tmp_path):
    return Settings(
        _env_file=None,
        runtime_config_path=None,
        user_secrets_enabled=False,
        organizational_memory_path=tmp_path / "memory.db",
        organizational_memory_enabled=False,
    )


def test_run_claims_ownership_exclusion_and_worker_recovery(tmp_path):
    store = SDLCStore(tmp_path / "memory.db")
    project = store.create("Delivery", "alice")["id"]
    run = store.create_run(project, "alice", {"brief": "Implement a verified delivery pipeline"})
    with pytest.raises(SDLCError, match="active"):
        store.create_run(project, "alice", {})
    with pytest.raises(SDLCError, match="Stop the active"):
        store.save(project, "alice", "planning", {"document": "Changed scope"}, 0, [])
    with pytest.raises(SDLCError, match="not found"):
        store.run(run["id"], "bob")
    assert store.claim_run(run["id"], "alice")["status"] == "running"
    with pytest.raises(SDLCError, match="claimed"):
        store.claim_run(run["id"], "alice")
    store.run_event(run["id"], "alice", "planning", "started", "running", "Planning owns task")
    with store.connect() as db:
        record = store.run(run["id"], "alice")
        record["updated_at"] = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
        db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(record), run["id"]))
    store.recover_runs("alice")
    reopened = SDLCStore(tmp_path / "memory.db").run(run["id"], "alice")
    assert reopened["status"] == "interrupted"
    assert reopened["events"][0]["message"] == "Planning owns task"


@pytest.mark.asyncio
async def test_coordinator_passes_exact_stage_handoffs_and_stops_at_target(tmp_path, monkeypatch):
    config = settings(tmp_path)
    store = SDLCStore(config.organizational_memory_path)
    project = store.create("Delivery", "alice")["id"]
    calls = []

    class Specialists:
        def __init__(self, *_):
            pass

        async def planning(self, context):
            calls.append("planning")
            return {"document": "Grounded planning output"}

        async def requirements(self, context):
            assert context["artifacts"]["planning"]["document"] == "Grounded planning output"
            calls.append("requirements")
            return {"document": "BA output grounded in the brief"}

        async def design(self, context):
            assert (
                context["artifacts"]["requirements"]["document"]
                == "BA output grounded in the brief"
            )
            calls.append("design")
            return {"document": "Architecture and interfaces"}

    monkeypatch.setattr("app.services.sdlc_delivery.SDLCStageAgents", Specialists)
    mission = DeliveryMission(brief="Build a verified agent delivery pipeline", target="design")
    run = store.create_run(project, "alice", mission.model_dump(mode="json"))
    await DeliveryCoordinator(config, store).execute(run["id"], "alice")
    result = store.run(run["id"], "alice")
    assert result["status"] == "completed"
    assert calls == ["planning", "requirements", "design"]
    assert result["artifact_versions"] == [{"stage": stage, "version": 1} for stage in calls]
    assert len(result["events"]) == 7
    assert store.snapshot(project, "alice")["artifacts"][0]["links"][0]["stage"] == "planning"


@pytest.mark.asyncio
async def test_failed_ba_gate_never_runs_development_or_release(tmp_path, monkeypatch):
    config = settings(tmp_path)
    store = SDLCStore(config.organizational_memory_path)
    project = store.create("Delivery", "alice")["id"]

    class Specialists:
        def __init__(self, *_):
            pass

        async def planning(self, context):
            return {"document": "Scope and questions"}

        async def requirements(self, context):
            raise StageBlocked("Missing approved API contract", {"question": "Supply the contract"})

    monkeypatch.setattr("app.services.sdlc_delivery.SDLCStageAgents", Specialists)
    mission = DeliveryMission(brief="Build a verified agent delivery pipeline", target="production")
    run = store.create_run(project, "alice", mission.model_dump(mode="json"))
    await DeliveryCoordinator(config, store).execute(run["id"], "alice")
    result = store.run(run["id"], "alice")
    assert result["status"] == "blocked"
    assert result["completed"] == ["planning"]
    assert result["blocking_evidence"] == {"question": "Supply the contract"}


def test_source_paths_and_task_cycles_fail_closed(tmp_path):
    for name in ("../escape.py", "/tmp/escape.py", ".env", "src/.env.production", ".git/config"):
        with pytest.raises(SDLCError):
            safe_path(tmp_path, name)
    (tmp_path / "linked").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(SDLCError):
        safe_path(tmp_path, "linked/escape.py")
    with pytest.raises(ValueError, match="cycle"):
        AgentDocument(
            title="Delivery plan",
            summary="Grounded plan with task dependencies",
            document="A delivery plan with traceable acceptance criteria.",
            tasks=[
                {
                    "id": "A1",
                    "title": "Implement architecture",
                    "acceptance_criteria": ["Reviewed"],
                    "depends_on": ["A2"],
                },
                {
                    "id": "A2",
                    "title": "Validate architecture",
                    "acceptance_criteria": ["Verified"],
                    "depends_on": ["A1"],
                },
            ],
        )


@pytest.mark.asyncio
async def test_isolated_checkout_and_repairs_preserve_trusted_source(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "app.py").write_text('print("original")\n')
    (repository / ".env").write_text("SECRET=must-not-export\n")
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=BDD",
            "-c",
            "user.email=bdd@example.test",
            "commit",
            "-qm",
            "Baseline",
        ],
        check=True,
    )
    config = settings(tmp_path).model_copy(update={"sdlc_repository_path": repository})
    tools = DeliveryTools(config, "project", "run")
    await tools.prepare()
    assert not (tools.checkout / ".env").exists()
    assert not (tools.root / "baseline.tar").exists()
    tools.write_files(
        [
            SourceFile(path="app.py", content='print("candidate")'),
            SourceFile(path="new.py", content='print("new")'),
        ]
    )
    await tools.reset_files(["app.py", "new.py"])
    assert (tools.checkout / "app.py").read_text() == 'print("original")\n'
    assert not (tools.checkout / "new.py").exists()
    assert (repository / "app.py").read_text() == 'print("original")\n'
    assert await tools.revision()


@pytest.mark.asyncio
async def test_deploy_receipts_revision_checks_and_secret_redaction(tmp_path):
    script = tmp_path / "deploy.py"
    script.write_text(
        "import os,json,pathlib\n"
        'pathlib.Path(os.environ["SDLC_RECEIPT_PATH"]).write_text(json.dumps({\n'
        '"environment":os.environ["SDLC_ENVIRONMENT"],\n'
        '"revision":os.environ["SDLC_REVISION"],\n'
        '"deployment_id":"simulated-deployment"}))\n'
    )
    config = settings(tmp_path).model_copy(
        update={"sdlc_preview_command": [sys.executable, str(script)]}
    )
    tools = DeliveryTools(config, "project", "run")
    tools.checkout.mkdir(parents=True)
    result = await tools.deploy("preview", "candidate-tree")
    assert result["receipt"]["revision"] == "candidate-tree"
    reused = await tools.deploy("preview", "candidate-tree")
    assert "not replayed" in reused["command"]["output"]
    with pytest.raises(SDLCError, match="does not match"):
        await tools.deploy("preview", "other-candidate")
    with pytest.raises(SDLCError, match="disabled"):
        await tools.deploy("production", "candidate-tree")


@pytest.mark.asyncio
async def test_health_requires_exact_deployed_revision(tmp_path, respx_mock, monkeypatch):
    tools = DeliveryTools(settings(tmp_path), "project", "run")
    endpoint = respx_mock.get("http://preview.test/health")
    endpoint.respond(200, json={"revision": "expected"})
    assert (await tools.health("http://preview.test/health", "expected"))["status"] == "healthy"
    endpoint.respond(200, json={"revision": "wrong-candidate"})

    async def no_wait(_):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_wait)
    with pytest.raises(SDLCError, match="candidate revision"):
        await tools.health("http://preview.test/health", "expected")


@pytest.mark.asyncio
async def test_resume_preserves_completed_handoffs_instead_of_regenerating(tmp_path, monkeypatch):
    config = settings(tmp_path)
    store = SDLCStore(config.organizational_memory_path)
    project = store.create("Resume delivery", "alice")["id"]
    attempts = []
    fail = True

    class Specialists:
        def __init__(self, *_):
            pass

        async def planning(self, context):
            attempts.append("planning")
            return {"document": "Delivery plan"}

        async def requirements(self, context):
            attempts.append("requirements")
            if fail:
                raise StageBlocked("Provider unavailable")
            return {"document": "Source-grounded BA output"}

        async def design(self, context):
            attempts.append("design")
            return {"document": "Reviewed architecture"}

    monkeypatch.setattr("app.services.sdlc_delivery.SDLCStageAgents", Specialists)
    mission = DeliveryMission(brief="Build a verified agent delivery pipeline")
    run = store.create_run(project, "alice", mission.model_dump(mode="json"))
    coordinator = DeliveryCoordinator(config, store)
    await coordinator.execute(run["id"], "alice")
    assert store.run(run["id"], "alice")["status"] == "blocked"
    fail = False
    store.resume_run(run["id"], "alice")
    await coordinator.execute(run["id"], "alice")
    assert attempts == ["planning", "requirements", "requirements", "design"]
    assert store.run(run["id"], "alice")["status"] == "completed"


@pytest.mark.asyncio
async def test_greenfield_agent_workspace_needs_no_existing_repository(tmp_path):
    config = settings(tmp_path).model_copy(update={"sdlc_greenfield_enabled": True})
    tools = DeliveryTools(config, "project", "run")
    assert (await tools.prepare())["base_commit"] == "greenfield"
    tools.write_files([SourceFile(path="app.py", content="print('agent scaffold')")])
    assert len(await tools.revision()) == 40


@pytest.mark.asyncio
async def test_release_rejects_results_for_a_different_candidate(tmp_path):
    from app.agents.sdlc_agent import SDLCStageAgents

    config = settings(tmp_path)
    tools = DeliveryTools(config, "project", "run")
    agent = SDLCStageAgents(
        config, DeliveryMission(brief="Deliver a verified quotation service"), tools
    )
    with pytest.raises(StageBlocked, match="exact source revision"):
        await agent.release(
            {
                "artifacts": {
                    "development": {"revision": "candidate"},
                    "testing": {"execution": {"revision": "other", "status": "passed"}},
                }
            }
        )


@pytest.mark.asyncio
async def test_failed_prod_health_rolls_back_and_verifies_previous_revision(tmp_path, monkeypatch):
    from app.agents.sdlc_agent import SDLCStageAgents

    config = settings(tmp_path).model_copy(
        update={
            "sdlc_production_enabled": True,
            "sdlc_production_command": ["configured-production-hook"],
            "sdlc_rollback_command": ["configured-rollback-hook"],
            "sdlc_production_health_url": "http://production.test/health",
            "sdlc_staging_health_url": "http://staging.test/health",
        }
    )
    actions = []

    class Tools:
        async def deploy(self, environment, revision):
            actions.append((environment, revision))
            return {
                "receipt": {"deployment_id": "simulated", "previous_revision": "previous-healthy"}
            }

        async def health(self, url, revision):
            actions.append(("health", revision))
            if url.startswith("http://production") and revision == "candidate":
                raise SDLCError("Candidate is unhealthy")
            return {"status": "healthy", "revision": revision}

    async def release_plan(*_):
        return {"document": "Simulated release plan for test verification"}

    agent = SDLCStageAgents(
        config,
        DeliveryMission(brief="Deliver a verified quotation service", target="production"),
        Tools(),
    )
    monkeypatch.setattr(agent, "document", release_plan)
    with pytest.raises(StageBlocked, match="rollback was verified") as failure:
        await agent.release(
            {
                "artifacts": {
                    "development": {"revision": "candidate"},
                    "testing": {"execution": {"revision": "candidate", "status": "passed"}},
                }
            }
        )
    assert actions == [
        ("staging", "candidate"),
        ("health", "candidate"),
        ("production", "candidate"),
        ("health", "candidate"),
        ("rollback", "previous-healthy"),
        ("health", "previous-healthy"),
    ]
    assert failure.value.evidence["rollback"]["health"]["revision"] == "previous-healthy"


@pytest.mark.asyncio
async def test_stop_prevents_the_next_promotion(tmp_path):
    tools = DeliveryTools(settings(tmp_path), "project", "run")
    tools.cancel_requested = lambda: True
    with pytest.raises(asyncio.CancelledError):
        await tools.deploy("production", "candidate")


def test_all_bdd_outline_rows_must_be_discovered_even_when_other_tests_pass():
    from app.services.sdlc_tools import bdd_coverage

    feature = """Feature: Candidate
      Scenario: Verify candidate health
        Then it is healthy
      Scenario Outline: Validate quote inputs
        Given a value "<value>"
        Examples:
          | value |
          | valid |
          | invalid |
    """
    assert (
        bdd_coverage(
            feature,
            ["VerifyCandidateHealth", "ValidateQuoteInputs(valid)", "ValidateQuoteInputs(invalid)"],
        )
        == []
    )
    assert bdd_coverage(
        feature, ["VerifyCandidateHealth", "ValidateQuoteInputs(valid)", "UnrelatedSmokeCheck"]
    ) == ["Validate quote inputs: expected 2 examples, found 1"]


@pytest.mark.asyncio
async def test_requirements_baseline_pins_outputs_and_invalidates_resume(tmp_path, monkeypatch):
    config = settings(tmp_path)
    store = SDLCStore(config.organizational_memory_path)
    project = store.create("Requirements-led delivery", "alice")["id"]
    source = {"document": "Approved requirements are the only product scope"}
    store.save(project, "alice", "requirements-input", source, 0, [])
    calls = []

    class Specialists:
        def __init__(self, *_):
            pass

        async def planning(self, context):
            assert context["mission"]["requirements_version"] == 1
            calls.append("planning")
            return {"document": "Grounded planning output"}

        async def requirements(self, context):
            raise StageBlocked("Clarify acceptance criteria in Requirements")

    monkeypatch.setattr("app.services.sdlc_delivery.SDLCStageAgents", Specialists)
    mission = DeliveryMission(brief=source["document"], requirements_version=1)
    run = store.create_run(project, "alice", mission.model_dump(mode="json"))
    await DeliveryCoordinator(config, store).execute(run["id"], "alice")
    output = next(
        item
        for item in store.snapshot(project, "alice")["artifacts"]
        if item["stage"] == "planning"
    )
    assert output["links"] == [{"stage": "requirements-input", "version": 1}]
    store.save(project, "alice", "requirements-input", source, 1, [])
    with pytest.raises(SDLCError, match="Requirements changed"):
        DeliveryCoordinator(config, store).resume(run["id"], "alice")
    with pytest.raises(SDLCError, match="Requirements changed"):
        store.create_run(project, "alice", mission.model_dump(mode="json"))
    assert store.run(run["id"], "alice")["status"] == "blocked"
    assert calls == ["planning"]


@pytest.mark.asyncio
async def test_launch_resolves_all_inputs_from_saved_requirements(tmp_path, monkeypatch):
    from app.sdlc_models import DeliveryStart
    from app.sdlc_routes import start_delivery

    config = settings(tmp_path)
    store = SDLCStore(config.organizational_memory_path)
    project = store.create("Single source", "alice")["id"]
    request = {
        "description": "Approved product requirements and acceptance criteria",
        "additional_context": "Use the approved integration contract",
        "llm_model": "codex",
    }
    store.save(
        project,
        "alice",
        "requirements-input",
        {"document": request["description"], "source_request": request},
        0,
        [],
    )

    class Recorder:
        def __init__(self, *_):
            pass

        def start(self, identifier, owner, mission):
            assert identifier == project and owner == "alice"
            return mission.model_dump(mode="json")

    monkeypatch.setattr("app.sdlc_routes.DeliveryCoordinator", Recorder)
    result = await start_delivery(
        project, DeliveryStart(requirements_version=1), store, "alice", config
    )
    assert result["brief"] == request["description"]
    assert result["constraints"] == request["additional_context"]
    assert result["source_request"]["description"] == request["description"]
    assert result["llm_model"] == "codex"
    assert result["requirements_version"] == 1


def test_ba_outputs_are_available_in_testing_workspace_before_testing(tmp_path):
    config = settings(tmp_path)
    store = SDLCStore(config.organizational_memory_path)
    project = store.create("BA handoff", "alice")["id"]
    request = {
        "description": "Approved requirements for BA story generation",
        "additional_context": "Approved constraints",
        "llm_model": "codex",
    }
    artifacts = {
        "requirements": {
            "request": request,
            "stories": {"stories": []},
            "ba_report": {},
            "requirements_report": {},
        }
    }
    DeliveryCoordinator(config, store).save_testing_handoff(project, "alice", artifacts)
    snapshot = store.snapshot(project, "alice")["artifacts"][0]["content"]
    assert snapshot["state"]["stage"] == 2
    assert snapshot["state"]["request"] == request
    assert snapshot["controls"]["sdlc-constraints"] == "Approved constraints"
    assert snapshot["suite"] is None
    assert snapshot["state"]["runReport"] is None
    assert snapshot["state"]["storiesReviewed"] is False
