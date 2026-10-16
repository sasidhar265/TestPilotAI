"""Versioned, project-scoped work items link delivery records to their source baseline."""

import json
from typing import Any
from uuid import uuid4

from app.lifecycle_workflow import WORKFLOW
from app.services.project_lifecycle import ProjectLifecycle, timestamp
from app.services.sdlc import SDLCError, SDLCStore

ITEM_TRANSITIONS = {
    "draft": {"ready", "blocked"},
    "ready": {"draft", "active", "blocked"},
    "active": {"resolved", "blocked"},
    "resolved": {"done", "active", "blocked"},
    "blocked": {"draft", "active"},
    "done": {"active"},
}

ITEM_ROLES = {
    "requirement": {"ba"},
    "epic": {"product_owner"},
    "story": {"product_owner", "developer"},
    "test_case": {"functional_tester", "automation_tester", "test_lead"},
    "defect": {"functional_tester", "automation_tester", "test_lead", "developer"},
    "release": {"release_manager"},
    "documentation": {"ba", "product_owner", "developer", "test_lead", "release_manager"},
}
ITEM_LINKS = {
    "requirement": set(),
    "epic": {"requirement"},
    "story": {"epic", "requirement", "story"},
    "test_case": {"story", "requirement"},
    "defect": {"story", "test_case"},
    "release": {"story", "test_case", "defect"},
    "documentation": {"requirement", "epic", "story", "test_case", "defect", "release"},
}


class ProjectWorkItems:
    def __init__(self, store: SDLCStore):
        self.store = store

    def list(self, project: str, actor: str) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            self.store.project(db, project, actor)
            baseline = ProjectLifecycle.state(db, project)["baseline"]
            rows = db.execute(
                "SELECT data FROM work_items WHERE project=? ORDER BY rowid", (project,)
            ).fetchall()
            records = {json.loads(row[0])["id"]: json.loads(row[0]) for row in rows}
            impacted = {key for key, item in records.items() if item["baseline"] != baseline}
            changed = True
            while changed:
                previous = impacted.copy()
                for key, item in records.items():
                    if any(
                        link in impacted or records.get(link, {}).get("version") != version
                        for link, version in item.get("link_versions", {}).items()
                    ):
                        impacted.add(key)
                changed = impacted != previous
            approvals: dict[str, int] = {}
            for row in db.execute(
                "SELECT data FROM lifecycle_events WHERE project=? ORDER BY sequence", (project,)
            ):
                event = json.loads(row[0])
                if event["action"] in {"source_changed", "requirement_changed"} or (
                    event.get("decision") == "changes_requested"
                    and list(WORKFLOW).index(event["target"])
                    <= list(WORKFLOW).index("stakeholder_approval")
                ):
                    approvals = {}
                if (
                    event.get("stage") == "stakeholder_approval"
                    and event.get("approval")
                    and event.get("baseline") == baseline
                ):
                    approvals = event.get("work_item_versions", {})
            return [
                dict(
                    item,
                    impacted=key in impacted,
                    approved=item["kind"] == "requirement"
                    and approvals.get(key) == item["version"],
                )
                for key, item in records.items()
            ]

    def save(
        self,
        project: str,
        actor: str,
        role: str,
        payload: dict[str, Any],
        assignee: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        kind = payload["kind"]
        if role != "admin" and role not in ITEM_ROLES[kind]:
            raise PermissionError("Your role cannot change this work item type")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.store.project(db, project, actor)
            state = ProjectLifecycle.state(db, project)
            if not state["baseline"]:
                raise SDLCError("Save Requirements before creating work items")
            identifier = payload.get("id") or uuid4().hex
            previous = db.execute(
                "SELECT data FROM work_items WHERE id=? AND project=?", (identifier, project)
            ).fetchone()
            current = json.loads(previous[0]) if previous else None
            if payload["base_version"] != (current["version"] if current else 0):
                raise SDLCError("A newer work item version exists. Reload before saving.")
            if current and current["kind"] != kind:
                raise SDLCError("Work item type cannot change")
            if payload["id"] and current is None:
                raise SDLCError("Work item not found")
            if (
                current
                and role == "developer"
                and kind == "story"
                and any(
                    payload[field] != current[field]
                    for field in (
                        "title",
                        "description",
                        "priority",
                        "estimate",
                        "acceptance_criteria",
                        "links",
                        "assignee",
                        "sprint",
                    )
                )
            ):
                raise PermissionError("Product owners govern story scope, priority and estimation")
            if not current and kind == "story" and role == "developer":
                raise PermissionError("Product owners create backlog stories")
            if kind == "defect" and payload["status"] == "done":
                if state["stage"] != "qa_retesting":
                    raise SDLCError("Defects close during QA retesting")
                retests = [
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT data FROM lifecycle_evidence WHERE project=? ORDER BY rowid",
                        (project,),
                    )
                ]
                current_retests = [
                    item
                    for item in retests
                    if item["kind"] == "retest"
                    and item["baseline"] == state["baseline"]
                    and item["created_at"] > state.get("rework_after", "")
                ]
                if not current_retests or current_retests[-1]["outcome"] != "passed":
                    raise SDLCError("Passing QA retest evidence is required to close a defect")
            if not current and payload["status"] != "draft":
                raise SDLCError("New work items start in draft")
            if (
                current
                and payload["status"] != current["status"]
                and payload["status"] not in ITEM_TRANSITIONS[current["status"]]
            ):
                raise SDLCError("Invalid work item status transition")
            link_versions = {}
            for link in payload["links"]:
                row = db.execute(
                    "SELECT data FROM work_items WHERE id=? AND project=?", (link, project)
                ).fetchone()
                linked = json.loads(row[0]) if row else None
                if not linked or linked["kind"] not in ITEM_LINKS[kind] or link == identifier:
                    raise SDLCError("Links must reference an allowed work item in this project")
                pending = list(linked["links"])
                visited = set()
                while pending:
                    dependency = pending.pop()
                    if dependency == identifier:
                        raise SDLCError("Work item links cannot contain a cycle")
                    if dependency not in visited:
                        visited.add(dependency)
                        record = db.execute(
                            "SELECT data FROM work_items WHERE id=? AND project=?",
                            (dependency, project),
                        ).fetchone()
                        if record:
                            pending.extend(json.loads(record[0])["links"])
                for dependency, expected in linked.get("link_versions", {}).items():
                    dependency_row = db.execute(
                        "SELECT data FROM work_items WHERE id=? AND project=?",
                        (dependency, project),
                    ).fetchone()
                    if (
                        dependency_row is None
                        or json.loads(dependency_row[0])["version"] != expected
                    ):
                        raise SDLCError("Revalidate impacted linked work items before using them")
                link_versions[link] = linked["version"]
                if linked["baseline"] != state["baseline"]:
                    raise SDLCError("Revalidate impacted linked work items before using them")
            if kind not in {"requirement", "documentation"} and not payload["links"]:
                raise SDLCError("A traceability link is required for this work item type")
            if payload["assignee"]:
                if not assignee or not assignee["enabled"]:
                    raise SDLCError("Assign an enabled project member")
                self.store.project(db, project, assignee["username"])
                if kind == "story" and assignee["role"] not in {"developer", "admin"}:
                    raise SDLCError("Stories must be assigned to a developer")
            if kind == "story" and payload["status"] in {"ready", "active", "resolved", "done"}:
                minimum = {
                    "ready": "prioritisation_estimation",
                    "active": "development",
                    "resolved": "development",
                    "done": "uat",
                }[payload["status"]]
                if list(WORKFLOW).index(state["stage"]) < list(WORKFLOW).index(minimum):
                    raise SDLCError(
                        "Complete the accountable lifecycle handoff before this story status"
                    )
            if kind == "story" and payload["status"] in {"ready", "active", "done"}:
                if not payload["acceptance_criteria"] or payload["estimate"] is None:
                    raise SDLCError("Ready stories require acceptance criteria and an estimate")
                if payload["status"] in {"active", "done"} and not payload["assignee"]:
                    raise SDLCError("Development requires an assigned developer")
            if kind == "defect" and payload["status"] == "done" and role == "developer":
                raise PermissionError("QA must close a defect after retesting")
            data = dict(
                payload,
                id=identifier,
                version=payload["base_version"] + 1,
                baseline=state["baseline"],
                link_versions=link_versions,
                author=actor,
                updated_at=timestamp(),
            )
            db.execute(
                "INSERT OR REPLACE INTO work_items VALUES (?,?,?)",
                (identifier, project, json.dumps(data)),
            )
            db.execute(
                "INSERT INTO work_item_versions VALUES (?,?,?,?)",
                (identifier, project, data["version"], json.dumps(data)),
            )
            ProjectLifecycle.event(
                db,
                project,
                dict(
                    action="work_item_saved",
                    actor=actor,
                    work_item=identifier,
                    version=data["version"],
                    baseline=state["baseline"],
                    created_at=data["updated_at"],
                ),
            )
            if kind == "requirement":
                state.update(
                    stage="requirements_analysis",
                    revision=state["revision"] + 1,
                    rework_after=data["updated_at"],
                )
                ProjectLifecycle.put(db, project, state)
                ProjectLifecycle.event(
                    db,
                    project,
                    dict(
                        action="requirement_changed",
                        actor=actor,
                        work_item=identifier,
                        created_at=data["updated_at"],
                    ),
                )
            if current and kind in {"epic", "story", "test_case"}:
                meaningful = any(
                    payload[field] != current[field]
                    for field in ("title", "description", "acceptance_criteria", "links")
                )
                if meaningful:
                    target = "qa_testing" if kind == "test_case" else "backlog_refinement"
                    if list(WORKFLOW).index(state["stage"]) < list(WORKFLOW).index(target):
                        target = state["stage"]
                    state.update(
                        stage=target,
                        revision=state["revision"] + 1,
                        rework_after=data["updated_at"],
                    )
                    ProjectLifecycle.put(db, project, state)
                    ProjectLifecycle.event(
                        db,
                        project,
                        dict(
                            action="workflow_reopened",
                            actor=actor,
                            target=target,
                            work_item=identifier,
                            created_at=data["updated_at"],
                        ),
                    )
            return data
