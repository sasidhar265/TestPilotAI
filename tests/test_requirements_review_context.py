"""Version-bound approval context uses server assessments, never client draft claims."""

import pytest
from test_project_lifecycle import reach

from app.models import GenerateRequest
from app.services.project_lifecycle import ProjectLifecycle
from app.services.requirements_reviews import record_assessment
from app.services.sdlc import SDLCError, SDLCStore


@pytest.fixture
def reviewed_project(tmp_path):
    store = SDLCStore(tmp_path / "memory.db")
    project = store.create("Source-bound business review", "ba-user")["id"]
    source = GenerateRequest(description="Quotation deposits must follow approved business rules.")
    store.save(
        project,
        "ba-user",
        "requirements-input",
        {"document": source.description, "source_request": source.model_dump(mode="json")},
        0,
        [],
    )
    return store, project, source, ProjectLifecycle(store)


def test_assessments_match_source_and_ignore_client_workflow_claims(reviewed_project):
    store, project, source, flow = reviewed_project
    store.save(
        project,
        "ba-user",
        "workflow",
        {"version": 1, "state": {}, "savedBaReport": {"outcome": "ready_for_business_review"}},
        0,
        [],
    )
    assert flow.snapshot(project, "ba-user", "admin")["approval_context"]["assessments"] == {}
    record_assessment(
        store,
        "ba-user",
        source,
        "business_analysis",
        {"summary": "Server-produced fixture review", "outcome": "ready_for_business_review"},
    )
    context = flow.snapshot(project, "ba-user", "admin")["approval_context"]
    assert context["source"]["version"] == 1
    assert context["assessments"]["business_analysis"]["origin"] == "server_assessment"
    assert context["assessments"]["business_analysis"]["actor"] == "ba-user"
    assert context["drafts_are_approval_evidence"] is False
    assert not context["decisions"]


def test_unrelated_accounts_and_changed_sources_cannot_supply_approval_context(reviewed_project):
    store, project, source, flow = reviewed_project
    record_assessment(store, "another-account", source, "alignment", {"status": "aligned"})
    assert not flow.snapshot(project, "ba-user", "admin")["approval_context"]["assessments"]
    record_assessment(store, "ba-user", source, "alignment", {"status": "aligned"})
    revised = source.model_copy(
        update={"description": "Changed BRD deposit and term requirements."}
    )
    store.save(
        project,
        "ba-user",
        "requirements-input",
        {"document": revised.description, "source_request": revised.model_dump(mode="json")},
        1,
        [],
    )
    context = flow.snapshot(project, "ba-user", "admin")["approval_context"]
    assert context["baseline"] == 2
    assert not context["assessments"]
    with pytest.raises(SDLCError, match="Project not found"):
        flow.snapshot(project, "another-account", "admin")


@pytest.mark.parametrize(
    "kind,report",
    [
        ("alignment", {"status": "blocked"}),
        ("business_analysis", {"outcome": "needs_clarification"}),
    ],
)
def test_blocked_review_prevents_approval_but_permits_human_rework(reviewed_project, kind, report):
    store, project, source, flow = reviewed_project
    reach(flow, project, "stakeholder_approval")
    record_assessment(store, "ba-user", source, kind, report)
    state = flow.snapshot(project, "ba-user", "business_stakeholder")
    assert state["approval_context"]["blockers"]
    payload = dict(revision=state["revision"], decision="approved", comment="Human fixture review")
    with pytest.raises(SDLCError):
        flow.transition(project, "ba-user", "business_stakeholder", payload, human=True)
    assert flow.snapshot(project, "ba-user", "admin")["stage"] == "stakeholder_approval"
    payload["decision"] = "changes_requested"
    flow.transition(project, "ba-user", "business_stakeholder", payload, human=True)
    state = flow.snapshot(project, "ba-user", "admin")
    assert state["stage"] == "clarification"
    assert state["approval_context"]["decisions"][-1]["human"] is True
    assert state["approval_context"]["decisions"][-1]["baseline"] == 1


def test_human_approval_history_retains_prior_versions_after_brd_change(reviewed_project):
    store, project, source, flow = reviewed_project
    reach(flow, project, "backlog_generation")
    first = flow.snapshot(project, "ba-user", "admin")["approval_context"]["decisions"][-1]
    assert first["actor"] == "ba-user" and first["human"]
    assert first["artifact_version"] == 1 and first["approval"]
    store.save(
        project,
        "ba-user",
        "requirements-input",
        {"document": source.description, "source_request": source.model_dump(mode="json")},
        1,
        [],
    )
    state = flow.snapshot(project, "ba-user", "admin")
    assert state["stage"] == "requirements_analysis"
    assert state["approval_context"]["baseline"] == 2
    assert state["approval_context"]["decisions"][-1]["baseline"] == 1


def test_new_server_assessment_invalidates_an_open_human_decision(reviewed_project):
    store, project, source, flow = reviewed_project
    reach(flow, project, "stakeholder_approval")
    opened = flow.snapshot(project, "ba-user", "business_stakeholder")
    record_assessment(store, "ba-user", source, "alignment", {"status": "aligned"})
    with pytest.raises(SDLCError, match="Lifecycle changed"):
        flow.transition(
            project,
            "ba-user",
            "business_stakeholder",
            {"revision": opened["revision"], "decision": "approved", "comment": "Opened earlier"},
            human=True,
        )
    current = flow.snapshot(project, "ba-user", "business_stakeholder")
    assert current["stage"] == "stakeholder_approval"
    assert current["revision"] > opened["revision"]
    assert current["audit"][-1]["action"] == "requirements_assessed"
