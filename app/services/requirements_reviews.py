"""Server-produced BRD assessments, matched to exact effective source and project membership."""

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.models import GenerateRequest
from app.services.sdlc import SDLCStore
from app.workspace_policy import apply_rules


def source_key(source: GenerateRequest) -> str:
    # Testing output preferences do not change the business source being assessed.
    data = apply_rules(source).model_dump(
        mode="json", exclude={"generation_target", "output_format", "manual_testing_type"}
    )
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def record_assessment(
    store: SDLCStore, actor: str, source: GenerateRequest, kind: str, report: dict[str, Any]
) -> None:
    if kind not in {"business_analysis", "alignment"}:
        raise ValueError("Unknown requirements assessment")
    identifier = uuid4().hex
    data = dict(
        id=identifier,
        origin="server_assessment",
        actor=actor,
        kind=kind,
        report=report,
        recorded_at=datetime.now(UTC).isoformat(),
    )
    key = source_key(source)
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO requirements_assessments VALUES (?,?,?,?,?)",
            (identifier, actor, key, kind, json.dumps(data)),
        )
        # A changed assessment is reviewable evidence. Invalidate an open decision's
        # optimistic revision without granting approval or advancing the workflow.
        rows = db.execute(
            "SELECT l.project,l.data,r.data FROM lifecycle l JOIN projects p ON p.id=l.project "
            "JOIN revisions r ON r.project=p.id AND r.stage='requirements-input' "
            "AND r.version=(SELECT MAX(version) FROM revisions WHERE project=p.id "
            "AND stage='requirements-input') WHERE p.owner=? OR EXISTS "
            "(SELECT 1 FROM project_members WHERE project=p.id AND username=?)",
            (actor, actor),
        ).fetchall()
        for project, raw_state, raw_artifact in rows:
            state, artifact = json.loads(raw_state), json.loads(raw_artifact)
            candidate = artifact["content"].get("source_request", {})
            try:
                matches = source_key(GenerateRequest.model_validate(candidate)) == key
            except (OSError, ValueError):
                matches = False
            if not matches or artifact["version"] != state["baseline"]:
                continue
            state["revision"] += 1
            db.execute("UPDATE lifecycle SET data=? WHERE project=?", (json.dumps(state), project))
            event = dict(
                action="requirements_assessed",
                actor=actor,
                kind=kind,
                assessment_id=identifier,
                baseline=state["baseline"],
                created_at=data["recorded_at"],
                origin="server_assessment",
            )
            db.execute(
                "INSERT INTO lifecycle_events(project,data) VALUES (?,?)",
                (project, json.dumps(event)),
            )


def matching_assessments(
    db: sqlite3.Connection, project: str, source: dict[str, Any]
) -> dict[str, Any]:
    try:
        request = GenerateRequest.model_validate(source)
        key = source_key(request)
    except (OSError, ValueError):
        return {}
    rows = db.execute(
        "SELECT kind,data FROM requirements_assessments WHERE source_key=? AND "
        "(actor=(SELECT owner FROM projects WHERE id=?) OR actor IN "
        "(SELECT username FROM project_members WHERE project=?)) ORDER BY rowid",
        (key, project, project),
    )
    return {row[0]: json.loads(row[1]) for row in rows}


def approval_context(
    db: sqlite3.Connection, project: str, state: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    row = db.execute(
        "SELECT data FROM revisions WHERE project=? AND stage='requirements-input' AND version=?",
        (project, state["baseline"]),
    ).fetchone()
    source = json.loads(row[0]) if row else None
    assessments = matching_assessments(
        db, project, source["content"].get("source_request", {}) if source else {}
    )
    requirements = [
        json.loads(row[0])
        for row in db.execute("SELECT data FROM work_items WHERE project=?", (project,))
        if json.loads(row[0]).get("kind") == "requirement"
    ]
    decisions = [
        event
        for event in events
        if event.get("action") == "transition" and event.get("stage") == "stakeholder_approval"
    ]
    blockers = []
    from app.services.ba_reviews import review_blockers

    blockers.extend(review_blockers(db, project, state["baseline"]))
    if not source:
        blockers.append("Save a versioned BRD source before requesting business approval.")
    if assessments.get("alignment", {}).get("report", {}).get("status") == "blocked":
        blockers.append("The server's current-source alignment assessment is blocked.")
    if assessments.get("business_analysis", {}).get("report", {}).get("outcome") in {
        "blocked",
        "needs_clarification",
    }:
        blockers.append("Resolve the current-source BA/domain clarification findings first.")
    return dict(
        baseline=state["baseline"],
        source=source,
        assessments=assessments,
        requirements=requirements,
        decisions=decisions,
        blockers=blockers,
        review_origin="server_assessment",
        drafts_are_approval_evidence=False,
    )
