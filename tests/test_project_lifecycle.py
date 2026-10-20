"""Lifecycle journeys use local evidence; no provider or deployment success is simulated."""

import pytest

from app.lifecycle_workflow import WORKFLOW
from app.services.project_lifecycle import ProjectLifecycle
from app.services.sdlc import SDLCError, SDLCStore


@pytest.fixture
def project(tmp_path):
    store = SDLCStore(tmp_path / "memory.db")
    identifier = store.create("Governed delivery", "ba-user")["id"]
    store.save(identifier, "ba-user", "requirements-input", {"document": "Approved source"}, 0, [])
    return store, ProjectLifecycle(store), identifier


def advance(flow, identifier, decision="approved", role=None):
    state = flow.snapshot(identifier, "ba-user", "admin")
    policy = WORKFLOW[state["stage"]]
    role = role or policy["roles"][0]
    if decision == "approved":
        for kind in policy["evidence"]:
            flow.evidence(
                identifier,
                "ba-user",
                role,
                dict(
                    revision=state["revision"],
                    kind=kind,
                    reference="test-fixture://" + kind,
                    outcome="passed",
                    comment="Unit fixture attestation; not real execution",
                ),
            )
            state = flow.snapshot(identifier, "ba-user", role)
    return flow.transition(
        identifier,
        "ba-user",
        role,
        dict(revision=state["revision"], decision=decision, comment="Human fixture decision"),
        human=True,
    )


def reach(flow, identifier, target):
    for _ in range(30):
        if flow.snapshot(identifier, "ba-user", "admin")["stage"] == target:
            return
        advance(flow, identifier)
    pytest.fail("Target was not reached")


def test_complete_lifecycle_gates_persist_and_deployment_requires_human_approvals(project):
    store, flow, identifier = project
    with pytest.raises(SDLCError, match="Human release workflow"):
        flow.require_deployment(identifier, "ba-user", "production")
    reach(flow, identifier, "staging_validation")
    flow.require_deployment(identifier, "ba-user", "staging")
    reach(flow, identifier, "production_deployment")
    flow.require_deployment(identifier, "ba-user", "production")
    reach(flow, identifier, "closed")
    state = ProjectLifecycle(SDLCStore(store.path.parent / "memory.db")).snapshot(
        identifier, "ba-user", "admin"
    )
    assert state["stage"] == "closed"
    approvals = [e for e in state["audit"] if e.get("approval")]
    assert {e["stage"] for e in approvals} == {
        "stakeholder_approval",
        "qa_signoff",
        "release_approval",
        "production_approval",
    }
    assert all(e["actor"] and e["artifact_version"] == 1 and e["comment"] for e in approvals)


def test_rbac_missing_evidence_service_identity_and_stale_writes_fail(project):
    _, flow, identifier = project
    state = flow.snapshot(identifier, "ba-user", "ba")
    payload = dict(revision=state["revision"], decision="approved", comment="Reviewed")
    with pytest.raises(PermissionError, match="role"):
        flow.transition(identifier, "ba-user", "developer", payload, human=True)
    with pytest.raises(PermissionError, match="human"):
        flow.transition(identifier, "ba-user", "ba", payload, human=False)
    with pytest.raises(SDLCError, match="evidence"):
        flow.transition(identifier, "ba-user", "ba", payload, human=True)
    advance(flow, identifier)
    with pytest.raises(SDLCError, match="changed"):
        flow.transition(identifier, "ba-user", "ba", payload, human=True)
    with pytest.raises(SDLCError, match="not found"):
        flow.snapshot(identifier, "uninvited", "admin")


def test_rejection_and_defect_retest_return_to_accountable_owner(project):
    _, flow, identifier = project
    reach(flow, identifier, "stakeholder_approval")
    assert advance(flow, identifier, "changes_requested")["stage"] == "clarification"
    advance(flow, identifier)
    reach(flow, identifier, "qa_testing")
    assert advance(flow, identifier, "changes_requested")["stage"] == "defect_resolution"
    assert advance(flow, identifier)["stage"] == "qa_retesting"
    assert advance(flow, identifier)["stage"] == "qa_signoff"
    reach(flow, identifier, "staging_validation")
    flow.require_deployment(identifier, "ba-user", "staging")


def test_source_change_invalidates_downstream_evidence_and_resets_lifecycle(project):
    store, flow, identifier = project
    reach(flow, identifier, "production_deployment")
    store.save(identifier, "ba-user", "requirements-input", {"document": "Changed source"}, 1, [])
    state = flow.snapshot(identifier, "ba-user", "ba")
    assert state["stage"] == "requirements_analysis" and state["baseline"] == 2
    assert state["impacted_evidence"]
    assert state["missing_evidence"] == ["analysis"]
    with pytest.raises(SDLCError):
        flow.require_deployment(identifier, "ba-user", "production")


def test_explicit_project_membership_and_evidence_cannot_cross_projects(project):
    store, flow, identifier = project
    with store.connect() as db:
        db.execute("INSERT INTO project_members VALUES (?,?)", (identifier, "stakeholder"))
    assert store.projects("stakeholder")[0]["id"] == identifier
    assert flow.snapshot(identifier, "stakeholder", "business_stakeholder")["can_act"] is False
    other = store.create("Other", "other-user")["id"]
    with pytest.raises(SDLCError, match="not found"):
        flow.snapshot(other, "stakeholder", "business_stakeholder")


def test_failed_evidence_and_rework_do_not_reuse_old_passes(project):
    _, flow, identifier = project
    reach(flow, identifier, "ba_validation")
    advance(flow, identifier, "changes_requested")
    reach(flow, identifier, "ba_validation")
    state = flow.snapshot(identifier, "ba-user", "ba")
    assert state["missing_evidence"] == ["ba_validation"]
    flow.evidence(
        identifier,
        "ba-user",
        "ba",
        dict(
            revision=state["revision"],
            kind="ba_validation",
            reference="test-fixture://failed",
            outcome="failed",
            comment="Needs correction",
        ),
    )
    assert flow.snapshot(identifier, "ba-user", "ba")["missing_evidence"] == ["ba_validation"]


def item(kind, title, **overrides):
    return (
        dict(
            id=None,
            base_version=0,
            kind=kind,
            title=title,
            description="",
            status="draft",
            priority="medium",
            estimate=None,
            assignee="",
            sprint="",
            acceptance_criteria=[],
            links=[],
            references=[],
        )
        | overrides
    )


def test_work_items_link_versions_change_impact_and_defect_closure(project):
    from app.services.project_work_items import ProjectWorkItems

    store, flow, identifier = project
    items = ProjectWorkItems(store)
    requirement = items.save(identifier, "ba-user", "ba", item("requirement", "Requirement"))
    story = items.save(
        identifier, "ba-user", "product_owner", item("story", "Story", links=[requirement["id"]])
    )
    case = items.save(
        identifier, "ba-user", "test_lead", item("test_case", "Test", links=[story["id"]])
    )
    items.save(
        identifier, "ba-user", "ba", dict(requirement, base_version=1, title="Changed requirement")
    )
    records = {r["id"]: r for r in items.list(identifier, "ba-user")}
    assert records[story["id"]]["impacted"] and records[case["id"]]["impacted"]
    assert flow.snapshot(identifier, "ba-user", "ba")["stage"] == "requirements_analysis"
    with pytest.raises(SDLCError, match="newer"):
        items.save(identifier, "ba-user", "ba", dict(requirement, base_version=0))
    with pytest.raises(PermissionError):
        items.save(
            identifier,
            "ba-user",
            "developer",
            dict(story, base_version=1, title="Unapproved scope"),
        )
    with pytest.raises(SDLCError, match="Invalid work item"):
        items.save(
            identifier, "ba-user", "product_owner", dict(story, base_version=1, status="done")
        )


@pytest.mark.asyncio
async def test_unguarded_staging_command_is_never_executed(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from app.config import Settings
    from app.services.sdlc_tools import DeliveryTools

    config = Settings(
        _env_file=None, runtime_config_path=None, organizational_memory_path=tmp_path / "memory.db"
    )
    tools = DeliveryTools(config, "missing-project", "missing-run")
    command = AsyncMock()
    monkeypatch.setattr(tools, "command", command)
    with pytest.raises(SDLCError, match="governed"):
        await tools.deploy("staging", "candidate")
    command.assert_not_awaited()


def test_deployment_is_bound_to_the_human_reviewed_candidate_versions(project):
    store, flow, identifier = project
    reach(flow, identifier, "development")
    store.save(
        identifier,
        "ba-user",
        "development",
        {"document": "Unit implementation fixture", "revision": "unit-candidate"},
        0,
        [],
    )
    store.save(
        identifier,
        "ba-user",
        "testing",
        {
            "document": "Unit test fixture",
            "execution": {"revision": "unit-candidate", "status": "passed"},
        },
        0,
        [],
    )
    reach(flow, identifier, "staging_validation")
    flow.require_deployment(identifier, "ba-user", "staging", "unit-candidate")
    with pytest.raises(SDLCError, match="successfully tested revision"):
        flow.require_deployment(identifier, "ba-user", "staging", "different-candidate")
    store.save(
        identifier,
        "ba-user",
        "testing",
        {
            "document": "Changed unit test fixture",
            "execution": {"revision": "unit-candidate", "status": "passed"},
        },
        1,
        [],
    )
    with pytest.raises(SDLCError, match="human approvals"):
        flow.require_deployment(identifier, "ba-user", "staging", "unit-candidate")


@pytest.mark.asyncio
async def test_agent_cannot_start_development_ahead_of_human_workflow(project, monkeypatch):
    from app.config import Settings
    from app.sdlc_models import DeliveryMission
    from app.services.sdlc_delivery import DeliveryCoordinator

    store, _, identifier = project

    class Specialists:
        def __init__(self, *_):
            pass

        async def planning(self, _):
            return {"document": "Unit planning suggestion"}

        async def requirements(self, _):
            return {"document": "Unit requirements suggestion"}

        async def design(self, _):
            return {"document": "Unit design suggestion"}

    monkeypatch.setattr("app.services.sdlc_delivery.SDLCStageAgents", Specialists)
    config = Settings(
        _env_file=None,
        runtime_config_path=None,
        organizational_memory_path=store.path.parent / "memory.db",
    )
    mission = DeliveryMission(brief="Unit agent human handoff fixture", target="tested")
    run = store.create_run(identifier, "ba-user", mission.model_dump(mode="json"))
    await DeliveryCoordinator(config, store).execute(run["id"], "ba-user")
    result = store.run(run["id"], "ba-user")
    assert result["status"] == "blocked"
    assert result["completed"] == ["planning", "requirements", "design"]
    assert "human workflow gates through development" in result["error"]


def test_editing_draft_story_never_skips_upstream_human_gates(project):
    from app.services.project_work_items import ProjectWorkItems

    store, flow, identifier = project
    items = ProjectWorkItems(store)
    source = items.save(identifier, "ba-user", "ba", item("requirement", "Source"))
    story = items.save(
        identifier, "ba-user", "product_owner", item("story", "Story", links=[source["id"]])
    )
    items.save(
        identifier,
        "ba-user",
        "product_owner",
        dict(story, base_version=1, title="Revised draft story"),
    )
    assert flow.snapshot(identifier, "ba-user", "ba")["stage"] == "requirements_analysis"


def test_sequential_workspace_metadata_covers_all_stages_and_rework(project):
    from app.lifecycle_workflow import PHASES

    store, flow, identifier = project
    assert [phase["id"] for phase in PHASES] == [
        "requirements",
        "business-approval",
        "backlog",
        "development",
        "qa",
        "release",
        "deployment",
        "closure",
    ]
    stages = [stage for phase in PHASES for stage in phase["stages"]]
    assert len(stages) == len(set(stages)) == len(WORKFLOW)
    assert set(stages) == set(WORKFLOW)
    assert flow.snapshot(identifier, "ba-user", "ba")["phase"] == "requirements"
    reach(flow, identifier, "stakeholder_approval")
    assert (
        flow.snapshot(identifier, "ba-user", "business_stakeholder")["phase"] == "business-approval"
    )
    advance(flow, identifier, "changes_requested")
    assert flow.snapshot(identifier, "ba-user", "ba")["phase"] == "business-approval"
    assert store.snapshot(identifier, "ba-user")["project"]["id"] == identifier
