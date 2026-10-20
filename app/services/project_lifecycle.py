"""Atomic project lifecycle transitions and version-bound human evidence."""

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.lifecycle_workflow import GATES, PHASES, WORKFLOW, can_act
from app.services.ba_handoff import backlog_drafting
from app.services.requirements_reviews import approval_context
from app.services.sdlc import SDLCError, SDLCStore


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


class ProjectLifecycle:
    def __init__(self, store: SDLCStore):
        self.store = store

    @staticmethod
    def state(db: sqlite3.Connection, project: str) -> dict[str, Any]:
        row = db.execute("SELECT data FROM lifecycle WHERE project=?", (project,)).fetchone()
        return json.loads(row[0]) if row else dict(stage="brd_upload", revision=0, baseline=0)

    @staticmethod
    def put(db: sqlite3.Connection, project: str, data: dict[str, Any]) -> None:
        db.execute("INSERT OR REPLACE INTO lifecycle VALUES (?,?)", (project, json.dumps(data)))

    @staticmethod
    def event(db: sqlite3.Connection, project: str, data: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO lifecycle_events(project,data) VALUES (?,?)", (project, json.dumps(data))
        )

    @classmethod
    def source_changed(cls, db: sqlite3.Connection, project: str, version: int, actor: str) -> None:
        state = cls.state(db, project)
        previous = state.copy()
        state.update(
            stage="requirements_analysis", revision=state["revision"] + 1, baseline=version
        )
        cls.put(db, project, state)
        cls.event(
            db,
            project,
            dict(
                id=uuid4().hex,
                action="source_changed",
                actor=actor,
                previous=previous,
                current=state,
                created_at=timestamp(),
                comment="Downstream evidence and approvals require review against the new baseline",
            ),
        )

    def snapshot(self, project: str, actor: str, role: str) -> dict[str, Any]:
        from app.services.project_work_items import ITEM_LINKS, ITEM_ROLES, ITEM_TRANSITIONS

        with self.store.connect() as db:
            self.store.project(db, project, actor)
            state = self.state(db, project)
            evidence = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT data FROM lifecycle_evidence WHERE project=? ORDER BY rowid", (project,)
                )
            ]
            events = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT data FROM lifecycle_events WHERE project=? ORDER BY sequence",
                    (project,),
                )
            ]
            policy = WORKFLOW[state["stage"]]
            current = [
                item
                for item in evidence
                if item["baseline"] == state["baseline"]
                and item["stage"] == state["stage"]
                and item["created_at"] > state.get("rework_after", "")
            ]
            latest = {item["kind"]: item for item in current}
            missing = [
                kind
                for kind in policy["evidence"]
                if latest.get(kind, {}).get("outcome") != "passed"
            ]
            return dict(
                **state,
                definition=list(WORKFLOW.values()),
                phases=list(PHASES),
                phase=policy["phase"],
                evidence=evidence,
                audit=events,
                missing_evidence=missing,
                can_act=can_act(role, state["stage"]),
                pending_approval=policy["human_approval"],
                approval_context=approval_context(db, project, state, events),
                item_transitions={key: sorted(value) for key, value in ITEM_TRANSITIONS.items()},
                item_links={key: sorted(value) for key, value in ITEM_LINKS.items()},
                backlog_drafting=backlog_drafting(db, project, state["baseline"], role),
                work_item_types=[
                    kind for kind, roles in ITEM_ROLES.items() if role == "admin" or role in roles
                ],
                impacted_evidence=[
                    item["id"]
                    for item in evidence
                    if item["baseline"] != state["baseline"]
                    or item["created_at"] <= state.get("rework_after", "")
                ],
            )

    def evidence(
        self, project: str, actor: str, role: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.store.project(db, project, actor)
            state = self.state(db, project)
            if not can_act(role, state["stage"]):
                raise PermissionError("Only the accountable stage owner can record evidence")
            if payload["revision"] != state["revision"]:
                raise SDLCError("Lifecycle changed. Reload before recording evidence.")
            if payload["kind"] not in WORKFLOW[state["stage"]]["evidence"]:
                raise SDLCError("Evidence kind does not belong to the current stage")
            if not state["baseline"]:
                raise SDLCError("Save Requirements before recording evidence")
            data = dict(
                **payload,
                id=uuid4().hex,
                actor=actor,
                role=role,
                stage=state["stage"],
                baseline=state["baseline"],
                created_at=timestamp(),
                source="human_attestation",
            )
            db.execute(
                "INSERT INTO lifecycle_evidence VALUES (?,?,?)",
                (data["id"], project, json.dumps(data)),
            )
            state["revision"] += 1
            self.put(db, project, state)
            self.event(db, project, dict(action="evidence_recorded", **data))
            return data

    def transition(
        self, project: str, actor: str, role: str, payload: dict[str, Any], *, human: bool
    ) -> dict[str, Any]:
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.store.project(db, project, actor)
            state = self.state(db, project)
            stage = state["stage"]
            policy = WORKFLOW[stage]
            if not can_act(role, stage):
                raise PermissionError("Your role cannot transition this stage")
            if payload["revision"] != state["revision"]:
                raise SDLCError("Lifecycle changed. Reload before transitioning.")
            if not human:
                raise PermissionError("Lifecycle decisions require an authenticated human session")
            if not state["baseline"]:
                raise SDLCError("Save Requirements before advancing")
            rejected = payload["decision"] == "changes_requested"
            if stage == "ba_validation" and not rejected:
                from app.services.ba_reviews import review_blockers

                blockers = review_blockers(db, project, state["baseline"])
                if blockers:
                    raise SDLCError(" ".join(blockers))
            if stage == "stakeholder_approval" and not rejected:
                context = approval_context(db, project, state, [])
                if context["blockers"]:
                    raise SDLCError(" ".join(context["blockers"]))
            target = policy["reject_to"] if rejected else policy["next"]
            if target is None:
                raise SDLCError("No allowed transition from this stage")
            if not rejected and stage in {
                "qa_signoff",
                "uat",
                "release_approval",
                "production_approval",
            }:
                records = [
                    json.loads(row[0])
                    for row in db.execute("SELECT data FROM work_items WHERE project=?", (project,))
                ]
                if any(item["kind"] == "defect" and item["status"] != "done" for item in records):
                    raise SDLCError("QA must close all linked defects before sign-off or release")
            if not rejected:
                latest = {}
                for row in db.execute(
                    "SELECT data FROM lifecycle_evidence WHERE project=? ORDER BY rowid", (project,)
                ):
                    item = json.loads(row[0])
                    if (
                        item["stage"] == stage
                        and item["baseline"] == state["baseline"]
                        and item["created_at"] > state.get("rework_after", "")
                    ):
                        latest[item["kind"]] = item
                if any(
                    latest.get(kind, {}).get("outcome") != "passed" for kind in policy["evidence"]
                ):
                    raise SDLCError(
                        "Passing current-baseline evidence is required before advancement"
                    )
            work_item_versions = {
                row[0]: json.loads(row[1])["version"]
                for row in db.execute("SELECT id,data FROM work_items WHERE project=?", (project,))
            }
            artifact_versions = {}
            for row in db.execute(
                "SELECT stage,MAX(version) FROM revisions WHERE project=? GROUP BY stage",
                (project,),
            ):
                if row[0] != "workflow":
                    artifact_versions[row[0]] = row[1]
            event = dict(
                id=uuid4().hex,
                action="transition",
                actor=actor,
                role=role,
                stage=stage,
                target=target,
                baseline=state["baseline"],
                artifact_version=state["baseline"],
                artifact_versions=artifact_versions,
                work_item_versions=work_item_versions,
                assessment_ids={
                    kind: data["id"]
                    for kind, data in approval_context(db, project, state, [])[
                        "assessments"
                    ].items()
                }
                if stage == "stakeholder_approval"
                else {},
                work_item=project,
                decision=payload["decision"],
                comment=payload["comment"],
                human=True,
                approval=stage in GATES and not rejected,
                created_at=timestamp(),
            )
            state.update(stage=target, revision=state["revision"] + 1)
            # Rework invalidates all downstream decisions/evidence by starting a new evidence epoch.
            if rejected:
                state["rework_after"] = event["created_at"]
            self.put(db, project, state)
            self.event(db, project, event)
            return state

    def require_deployment(
        self, project: str, actor: str, environment: str, revision: str | None = None
    ) -> None:
        with self.store.connect() as db:
            self.store.project(db, project, actor)
            state = self.state(db, project)
            required = {"staging": "staging_validation", "production": "production_deployment"}
            if state["stage"] != required[environment]:
                raise SDLCError(
                    f"Human release workflow must reach {required[environment]} before deployment"
                )
            if approval_context(db, project, state, [])["blockers"]:
                raise SDLCError(
                    "Resolve current-source requirements review blockers before deployment"
                )
            if revision is not None:
                candidate = {}
                for stage in ("development", "testing"):
                    row = db.execute(
                        "SELECT data FROM revisions WHERE project=? AND stage=? "
                        "ORDER BY version DESC LIMIT 1",
                        (project, stage),
                    ).fetchone()
                    if row is None:
                        raise SDLCError("Versioned implementation and test execution are required")
                    candidate[stage] = json.loads(row[0])["content"]
                execution = candidate["testing"].get("execution", {})
                if (
                    candidate["development"].get("revision") != revision
                    or execution.get("revision") != revision
                    or execution.get("status") != "passed"
                ):
                    raise SDLCError(
                        "Deployment must match the implemented and successfully tested revision"
                    )
            gates = {"stakeholder_approval", "qa_signoff", "release_approval"}
            if environment == "production":
                gates.add("production_approval")
            approved: set[str] = set()
            versions = dict(
                db.execute(
                    "SELECT stage,MAX(version) FROM revisions WHERE project=? GROUP BY stage",
                    (project,),
                )
            )
            for row in db.execute(
                "SELECT data FROM lifecycle_events WHERE project=? ORDER BY sequence", (project,)
            ):
                event = json.loads(row[0])
                if event["action"] in {"source_changed", "requirement_changed"}:
                    approved.clear()
                if (
                    event.get("decision") == "changes_requested"
                    or event["action"] == "workflow_reopened"
                ):
                    order = list(WORKFLOW)
                    cutoff = order.index(event["target"])
                    approved = {gate for gate in approved if order.index(gate) < cutoff}
                if (
                    event.get("approval")
                    and event.get("human")
                    and event.get("baseline") == state["baseline"]
                ):
                    relevant = {
                        "stakeholder_approval": {"requirements-input", "requirements"},
                        "qa_signoff": {"requirements-input", "development", "testing"},
                        "release_approval": {
                            "requirements-input",
                            "development",
                            "testing",
                            "release",
                        },
                        "production_approval": {
                            "requirements-input",
                            "development",
                            "testing",
                            "release",
                        },
                    }[event["stage"]]
                    captured = event.get("artifact_versions", {})
                    if (
                        revision is not None
                        and event["stage"] != "stakeholder_approval"
                        and not {"development", "testing"} <= captured.keys()
                    ):
                        continue
                    if all(
                        versions.get(stage) == version
                        for stage, version in event.get("artifact_versions", {}).items()
                        if stage in relevant
                    ):
                        approved.add(event["stage"])
            if not gates <= approved:
                raise SDLCError("Current-baseline human approvals are required before deployment")
