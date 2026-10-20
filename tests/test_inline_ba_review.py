"""Real store/approval checks with explicitly synthetic provider output, never live AI evidence."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.agents.inline_business_analyst import (
    InlineBusinessAnalyst,
    source_sections,
    stable_output,
    validate_output,
)
from app.ba_review_models import BAReviewOutput, FindingDecision, ReviewSignoff, ReviewStart
from app.config import Settings
from app.models import GenerateRequest
from app.sdlc_routes import WorkItemInput
from app.services.ba_reviews import BAReviews, review_blockers
from app.services.project_lifecycle import ProjectLifecycle
from app.services.project_work_items import ProjectWorkItems
from app.services.sdlc import SDLCError, SDLCStore

FIXTURES = json.loads(
    (Path(__file__).parents[1] / "automation/Input/InlineBAReview.Json").read_text()
)


@pytest.mark.parametrize("case", FIXTURES["cases"], ids=lambda case: case["name"])
def test_acceptance_output_schema_evidence_and_readiness(case):
    output = BAReviewOutput.model_validate(case["output"])
    validate_output(output, source_sections(case["document"]), [])
    assert output.findings[0].finding_type == case["expected_type"]
    assert stable_output(output) == stable_output(output)
    if output.findings[0].finding_type in {"CALCULATION_GAP", "COMPLIANCE_REVIEW_REQUIRED"}:
        assert output.readiness_status == "BLOCKED"


def test_fabricated_sources_and_ai_approval_are_rejected():
    case = FIXTURES["cases"][0]
    output = BAReviewOutput.model_validate(case["output"])
    output.findings[0].evidence_references[0].section_id = "PAGE-999"
    with pytest.raises(ValueError, match="verified"):
        validate_output(output, source_sections(case["document"]), [])
    with pytest.raises(ValueError):
        BAReviewOutput.model_validate({**case["output"], "readiness_status": "APPROVED"})


@pytest.mark.parametrize("verified", [True, False])
def test_delivery_benefits_are_anchored_to_the_brd(verified):
    case = FIXTURES["cases"][0]
    output = BAReviewOutput.model_validate(
        {
            **case["output"],
            "business_deliverables": [
                {
                    "expectation": "Clarify the supplied quotation requirements",
                    "deliverable": "Reviewed quotation requirements",
                    "business_benefit": "Clearer delivery expectations",
                    "delivery_impact": "Resolve the requirement before implementation",
                    "benefit_basis": "inferred_requires_confirmation",
                    "success_measure": None,
                    "document_quote": case["document"]
                    if verified
                    else "Invented business outcome.",
                }
            ],
        }
    )
    if not verified:
        with pytest.raises(ValueError, match="business deliverable BRD quotation"):
            validate_output(output, source_sections(case["document"]), [])
        return
    checked = validate_output(output, source_sections(case["document"]), [])
    assert checked.business_deliverables[0].success_measure is None
    assert stable_output(checked)["business_deliverables"][0]["document_quote"] == case["document"]


@pytest.fixture
def review(tmp_path, monkeypatch):
    settings = Settings(organizational_memory_path=tmp_path / "memory.db")
    store = SDLCStore(settings.organizational_memory_path)
    project = store.create("Synthetic BA project", "ba-user")["id"]
    case = FIXTURES["cases"][6]
    request = GenerateRequest(description=case["document"], llm_model="codex")
    store.save(
        project,
        "ba-user",
        "requirements-input",
        dict(document=request.description, source_request=request.model_dump(mode="json")),
        0,
        [],
    )
    output = stable_output(
        validate_output(
            BAReviewOutput.model_validate(case["output"]), source_sections(case["document"]), []
        )
    )
    analyse = AsyncMock(return_value=output)
    monkeypatch.setattr(InlineBusinessAnalyst, "analyse", analyse)
    service = BAReviews(store, settings)
    run, created = service.start(project, "ba-user", "ba", ReviewStart(baseline=1), human=True)
    assert created
    asyncio.run(service.execute(project, "ba-user", run["id"]))
    return service, project, service.snapshot(project, "ba-user")["run"], analyse


def decision(run, action="reject", **extra):
    finding = run["output"]["findings"][0]
    return FindingDecision(
        revision=run["revision"],
        finding_id=finding["finding_id"],
        finding_version=finding["version"],
        action=action,
        comment="Synthetic BA decision with explicit rationale.",
        **extra,
    )


def test_completed_analysis_populates_source_linked_drafts_and_real_history(review):
    service, project, run, _ = review
    records = ProjectWorkItems(service.store).list(project, "ba-user")
    assert len(records) == len(run["output"]["requirements"])
    for record in records:
        assert record["status"] == "draft" and not record["approved"]
        assert record["ai_origin"]["review_id"] == run["id"]
        assert record["ai_origin"]["human"] is False
        assert record["author"] == "BA Agent"
        assert record["references"] and record["baseline"] == run["baseline"]
    state = ProjectLifecycle(service.store).snapshot(project, "ba-user", "ba")
    events = [event for event in state["audit"] if event["action"] == "ai_requirements_drafted"]
    assert len(events) == 1 and events[0]["human"] is False
    assert set(events[0]["work_items"]) == {record["id"] for record in records}
    assert state["stage"] == "requirements_analysis"
    assert not state["evidence"] and run["signoff"] is None


def test_reanalysis_preserves_human_edits_manual_records_and_draft_identity(review):
    service, project, run, _ = review
    records = ProjectWorkItems(service.store)
    original = records.list(project, "ba-user")[0]
    edited = records.save(
        project,
        "ba-user",
        "ba",
        WorkItemInput.model_validate(
            {
                **original,
                "base_version": original["version"],
                "title": "Human-reviewed draft wording",
            }
        ).model_dump(),
    )
    manual = records.save(
        project,
        "ba-user",
        "ba",
        WorkItemInput(
            base_version=0,
            kind="requirement",
            title="Manually entered requirement",
        ).model_dump(),
    )
    rerun, _ = service.start(
        project, "ba-user", "ba", ReviewStart(baseline=1, force=True), human=True
    )
    asyncio.run(service.execute(project, "ba-user", rerun["id"]))
    stored = {item["id"]: item for item in records.list(project, "ba-user")}
    assert len(stored) == 2
    assert stored[edited["id"]]["title"] == "Human-reviewed draft wording"
    assert stored[edited["id"]]["version"] == edited["version"]
    assert stored[edited["id"]]["ai_origin"] == original["ai_origin"]
    assert stored[manual["id"]]["title"] == manual["title"]
    current = service.snapshot(project, "ba-user")["run"]
    assert current["supporting_records"]["created"] == []
    assert current["supporting_records"]["existing"] == [original["id"]]


def test_new_brd_version_keeps_old_drafts_as_impacted_history(review):
    service, project, run, _ = review
    service.store.save(
        project,
        "ba-user",
        "requirements-input",
        {
            "document": run["request"]["description"],
            "source_request": run["request"],
        },
        1,
        [],
    )
    rerun, _ = service.start(project, "ba-user", "ba", ReviewStart(baseline=2), human=True)
    asyncio.run(service.execute(project, "ba-user", rerun["id"]))
    records = ProjectWorkItems(service.store).list(project, "ba-user")
    assert len(records) == 2
    old = next(item for item in records if item["baseline"] == 1)
    new = next(item for item in records if item["baseline"] == 2)
    assert old["impacted"] and not new["impacted"]
    assert old["id"] != new["id"] and not new["approved"]


def test_rejected_suggestion_persists_without_changing_brd_or_reapplying(review):
    service, project, run, analyse = review
    run = service.decide(project, "ba-user", "ba", run["id"], decision(run), human=True)
    assert run["output"]["findings"][0]["review_status"] == "REJECTED"
    cached, created = service.start(project, "ba-user", "ba", ReviewStart(baseline=1), human=True)
    assert cached["id"] == run["id"] and not created
    new, created = service.start(
        project, "ba-user", "ba", ReviewStart(baseline=1, force=True), human=True
    )
    asyncio.run(service.execute(project, "ba-user", new["id"]))
    restored = service.snapshot(project, "ba-user")["run"]
    assert restored["output"]["findings"][0]["review_status"] == "REJECTED"
    assert analyse.await_count == 2
    with service.store.connect() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM revisions WHERE project=? AND stage='requirements-input'",
                (project,),
            ).fetchone()[0]
            == 1
        )
    assert service.snapshot(project, "ba-user", run["id"])["run"]["decisions"][0]["human"]


def test_role_membership_stale_decisions_signoff_and_baseline_impact(review):
    service, project, run, _ = review
    with pytest.raises(SDLCError, match="Project not found"):
        service.snapshot(project, "outsider")
    for role, human in [("developer", True), ("ba", False)]:
        with pytest.raises(PermissionError):
            service.decide(project, "ba-user", role, run["id"], decision(run), human=human)
    with pytest.raises(SDLCError, match="resolve or reject"):
        service.signoff(
            project,
            "ba-user",
            "ba",
            run["id"],
            ReviewSignoff(revision=run["revision"], comment="Review complete"),
            human=True,
        )
    rejected = service.decide(project, "ba-user", "ba", run["id"], decision(run), human=True)
    with pytest.raises(SDLCError, match="changed"):
        service.decide(project, "ba-user", "ba", run["id"], decision(run), human=True)
    signed = service.signoff(
        project,
        "ba-user",
        "ba",
        run["id"],
        ReviewSignoff(
            revision=rejected["revision"],
            comment="BA checked the source and rejected the unsupported proposal",
        ),
        human=True,
    )
    assert signed["signoff"]["human"]
    with service.store.connect() as db:
        assert not review_blockers(db, project, 1)
    baseline = next(
        item
        for item in service.store.snapshot(project, "ba-user")["artifacts"]
        if item["stage"] == "requirements-input"
    )
    service.store.save(project, "ba-user", "requirements-input", baseline["content"], 1, [])
    with service.store.connect() as db:
        assert review_blockers(db, project, 2)
    assert service.snapshot(project, "ba-user")["impacted_runs"] == [run["id"]]
    with pytest.raises(SDLCError, match="superseded"):
        service.decide(project, "ba-user", "ba", run["id"], decision(signed), human=True)


def test_blocked_analysis_cannot_be_signed_off_by_resolving_findings(review):
    service, project, run, _ = review
    with service.store.connect() as db:
        run["output"]["readiness_status"] = "BLOCKED"
        service.put(db, run)
    resolved = service.decide(
        project, "ba-user", "ba", run["id"], decision(run, "resolve"), human=True
    )
    with pytest.raises(SDLCError, match="reanalysis"):
        service.signoff(
            project,
            "ba-user",
            "ba",
            run["id"],
            ReviewSignoff(
                revision=resolved["revision"], comment="Cannot override a blocked analysis"
            ),
            human=True,
        )
    assert ProjectLifecycle(service.store).snapshot(project, "ba-user", "ba")["approval_context"][
        "blockers"
    ]


def test_provider_receives_in_house_sources_and_explicit_model(tmp_path):
    reviewer = InlineBusinessAnalyst(Settings())
    case = FIXTURES["cases"][0]
    output = BAReviewOutput.model_validate(case["output"])
    reviewer.runner.generate_structured = AsyncMock(return_value=output)
    request = GenerateRequest(description=case["document"], llm_model="codex")
    sources, _, limitations, _ = reviewer.review_knowledge(request)
    result = asyncio.run(
        reviewer.analyse(request, source_sections(request.description), sources, limitations)
    )
    call = reviewer.runner.generate_structured.call_args
    assert call.kwargs["llm_model"].value == "codex"
    assert any(
        source["id"].startswith("UK-AUTO-FINANCE:")
        for source in json.loads(call.kwargs["prompt"])["knowledge_sources"]
    )
    assert "UNTRUSTED" in call.kwargs["instructions"]
    assert result["readiness_status"] == "BLOCKED"


def test_cancel_and_provider_failure_are_persisted_without_approval(review, monkeypatch):
    service, project, _, _ = review
    pending, _ = service.start(
        project, "ba-user", "ba", ReviewStart(baseline=1, force=True), human=True
    )
    cancelled = service.cancel(project, "ba-user", "ba", pending["id"], human=True)
    asyncio.run(service.execute(project, "ba-user", pending["id"]))
    assert cancelled["status"] == "cancelled" and cancelled["output"] is None
    monkeypatch.setattr(
        InlineBusinessAnalyst,
        "analyse",
        AsyncMock(side_effect=RuntimeError("Sensitive source must not appear in errors")),
    )
    pending, _ = service.start(
        project, "ba-user", "ba", ReviewStart(baseline=1, force=True), human=True
    )
    asyncio.run(service.execute(project, "ba-user", pending["id"]))
    failed = service.snapshot(project, "ba-user")["run"]
    assert failed["status"] == "failed" and failed["signoff"] is None
    assert "Sensitive" not in failed["progress"]


def test_knowledge_changes_require_reanalysis_before_signoff(review, monkeypatch):
    service, project, run, _ = review
    run = service.decide(project, "ba-user", "ba", run["id"], decision(run), human=True)
    original = InlineBusinessAnalyst.review_knowledge

    def changed(self, request):
        sources, key, limitations, scope = original(self, request)
        return sources, key + "changed", limitations, scope

    monkeypatch.setattr(InlineBusinessAnalyst, "review_knowledge", changed)
    with pytest.raises(SDLCError, match="knowledge changed"):
        service.signoff(
            project,
            "ba-user",
            "ba",
            run["id"],
            ReviewSignoff(revision=run["revision"], comment="Human review"),
            human=True,
        )


def test_parallel_analysis_requests_are_idempotent_and_new_baselines_supersede_them(review):
    service, project, _, _ = review
    pending, created = service.start(
        project, "ba-user", "ba", ReviewStart(baseline=1, force=True), human=True
    )
    duplicate, duplicate_created = service.start(
        project, "ba-user", "ba", ReviewStart(baseline=1, force=True), human=True
    )
    assert created and not duplicate_created and pending["id"] == duplicate["id"]
    baseline = next(
        item
        for item in service.store.snapshot(project, "ba-user")["artifacts"]
        if item["stage"] == "requirements-input"
    )
    service.store.save(project, "ba-user", "requirements-input", baseline["content"], 1, [])
    new, created = service.start(project, "ba-user", "ba", ReviewStart(baseline=2), human=True)
    assert created and new["id"] != pending["id"]
    assert service.snapshot(project, "ba-user", pending["id"])["run"]["status"] == "cancelled"


def signed_review(service, project, run):
    run = service.decide(project, "ba-user", "ba", run["id"], decision(run), human=True)
    return service.signoff(
        project,
        "ba-user",
        "ba",
        run["id"],
        ReviewSignoff(
            revision=run["revision"], comment="Reviewed the current source and AI findings."
        ),
        human=True,
    )


def test_ba_backlog_drafting_requires_current_human_signoff(review):
    service, project, run, _ = review
    items = ProjectWorkItems(service.store)
    requirement = items.list(project, "ba-user")[0]
    payload = WorkItemInput(
        base_version=0, kind="story", title="Quotation expiry story", links=[requirement["id"]]
    ).model_dump()
    with pytest.raises(SDLCError, match="sign-off"):
        items.save(project, "ba-user", "ba", payload)
    signed_review(service, project, run)
    state = ProjectLifecycle(service.store).snapshot(project, "ba-user", "ba")
    assert state["backlog_drafting"]["allowed"]
    story = items.save(project, "ba-user", "ba", payload)
    assert story["status"] == "draft" and story["link_versions"] == {requirement["id"]: 1}
    with pytest.raises(PermissionError, match="product owners"):
        items.save(project, "ba-user", "ba", {**payload, "status": "ready"})
    assert (
        ProjectLifecycle(service.store).snapshot(project, "ba-user", "ba")["stage"]
        == state["stage"]
    )
    service.store.save(
        project,
        "ba-user",
        "requirements-input",
        {"source_request": run["request"], "document": run["request"]["description"]},
        1,
        [],
    )
    with pytest.raises(SDLCError, match="sign-off"):
        items.save(project, "ba-user", "ba", payload)


def test_business_documents_are_downloadable_source_backed_and_project_scoped(review):
    import io
    import zipfile

    from app.services.ba_documents import business_documents

    service, project, run, _ = review
    signed_review(service, project, run)
    data, filename, media = business_documents(service.store, project, "ba-user", "all")
    assert filename == "ba-review-v1-business-documents.zip" and media == "application/zip"
    with zipfile.ZipFile(io.BytesIO(data)) as pack:
        assert set(pack.namelist()) == {
            "business-review.md",
            "review-metrics.csv",
            "saved-brd.txt",
            "review-history.json",
        }
        assert pack.read("saved-brd.txt").decode() == run["request"]["description"]
        history = json.loads(pack.read("review-history.json"))
        assert history["reviews"][0]["signoff"]["human"]
        assert "Human BA sign-off,True" in pack.read("review-metrics.csv").decode()
    with pytest.raises(SDLCError, match="Project not found"):
        business_documents(service.store, project, "outsider", "all")


@pytest.mark.parametrize("action", ["accept", "edit", "reject", "clarify"])
def test_revised_brd_preserves_history_and_applies_only_human_decisions(review, action):
    service, project, run, _ = review
    original = service.store.snapshot(project, "ba-user")["artifacts"][0]["content"]["document"]
    changed = service.decide(
        project,
        "ba-user",
        "ba",
        run["id"],
        decision(run, action=action, proposed_text=FIXTURES["edited_proposal"]),
        human=True,
    )
    saved = service.revise_brd(
        project, "ba-user", "ba", changed["id"], changed["revision"], human=True
    )
    assert saved["version"] == 2
    metadata = saved["content"]["ba_revision"]
    assert bool(metadata["applied_findings"]) == (action in {"accept", "edit"})
    assert bool(metadata["pending_feedback"]) == (action == "clarify")
    if action == "edit":
        assert FIXTURES["edited_proposal"] in saved["content"]["document"]
    if action == "reject":
        assert saved["content"]["document"] == original
    versions = service.store.snapshot(project, "ba-user")["artifacts"]
    assert (
        next(item for item in versions if item["version"] == 1)["content"]["document"] == original
    )
    assert saved["content"]["source_request"]["llm_model"] == "codex"
    with pytest.raises(SDLCError):
        service.revise_brd(project, "ba-user", "ba", changed["id"], changed["revision"], human=True)


def test_pending_or_stale_review_cannot_create_a_brd_version(review):
    service, project, run, _ = review
    with pytest.raises(SDLCError, match="every suggestion"):
        service.revise_brd(project, "ba-user", "ba", run["id"], run["revision"], human=True)
    changed = service.decide(project, "ba-user", "ba", run["id"], decision(run), human=True)
    with pytest.raises(SDLCError, match="changed"):
        service.revise_brd(project, "ba-user", "ba", run["id"], run["revision"], human=True)
    with pytest.raises(PermissionError):
        service.revise_brd(
            project, "ba-user", "developer", run["id"], changed["revision"], human=True
        )


def test_review_revision_guard_prevents_a_concurrent_decision_from_being_lost(review, monkeypatch):
    service, project, run, _ = review
    changed = service.decide(project, "ba-user", "ba", run["id"], decision(run), human=True)
    save = service.store.save

    def racing_save(*args, **kwargs):
        service.decide(
            project, "ba-user", "ba", changed["id"], decision(changed, action="clarify"), human=True
        )
        return save(*args, **kwargs)

    monkeypatch.setattr(service.store, "save", racing_save)
    with pytest.raises(SDLCError, match="BA review changed"):
        service.revise_brd(project, "ba-user", "ba", changed["id"], changed["revision"], human=True)
    assert ProjectLifecycle(service.store).snapshot(project, "ba-user", "ba")["baseline"] == 1


def test_failed_revalidation_keeps_the_saved_version_without_approval(review, monkeypatch):
    from app.agents.business_analyst import BusinessAnalystAgent

    service, project, run, _ = review
    changed = service.decide(
        project, "ba-user", "ba", run["id"], decision(run, action="accept"), human=True
    )
    service.revise_brd(project, "ba-user", "ba", changed["id"], changed["revision"], human=True)
    current, _ = service.start(project, "ba-user", "ba", ReviewStart(baseline=2), human=True)
    provider = AsyncMock(side_effect=RuntimeError("Synthetic provider unavailable"))
    monkeypatch.setattr(BusinessAnalystAgent, "review", provider)
    asyncio.run(service.execute_revalidation(project, "ba-user", current["id"]))
    failed = service.snapshot(project, "ba-user")["run"]
    assert failed["status"] == "failed"
    assert failed["signoff"] is None
    assert provider.call_args.args[0].llm_model.value == "codex"
    state = ProjectLifecycle(service.store).snapshot(project, "ba-user", "ba")
    assert state["baseline"] == 2 and not state["backlog_drafting"]["signed_off"]
