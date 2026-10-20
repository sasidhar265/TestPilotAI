"""Contextual review of real, versioned project records and agent suggestions."""

import json
import sqlite3
from typing import Any
from uuid import uuid4

from app.services.project_lifecycle import ProjectLifecycle, timestamp
from app.services.project_work_items import ITEM_LINKS, ITEM_ROLES, ITEM_TRANSITIONS
from app.services.sdlc import SDLCError, SDLCStore

EDIT_FIELDS = (
    "title",
    "description",
    "status",
    "priority",
    "estimate",
    "assignee",
    "sprint",
    "acceptance_criteria",
    "links",
    "references",
)


class ProjectReviews:
    def __init__(self, store: SDLCStore):
        self.store = store

    @staticmethod
    def item(db: sqlite3.Connection, project: str, identifier: str) -> dict[str, Any]:
        row = db.execute(
            "SELECT data FROM work_items WHERE project=? AND id=?", (project, identifier)
        ).fetchone()
        if not row:
            raise SDLCError("Work item not found")
        return dict(json.loads(row[0]))

    @staticmethod
    def fields(item: dict[str, Any], role: str) -> list[str]:
        if role != "admin" and role not in ITEM_ROLES[item["kind"]]:
            return []
        if role == "developer" and item["kind"] == "story":
            return ["status", "references"]
        if role == "ba" and item["kind"] == "story":
            return [
                field for field in EDIT_FIELDS if field not in {"estimate", "assignee", "sprint"}
            ]
        return list(EDIT_FIELDS)

    @staticmethod
    def suggestions(db: sqlite3.Connection, project: str, baseline: int) -> list[dict[str, Any]]:
        rows = db.execute(
            "SELECT data FROM revisions WHERE project=? AND stage NOT IN "
            "('workflow','requirements-input') AND version=(SELECT MAX(r.version) "
            "FROM revisions r WHERE r.project=revisions.project AND r.stage=revisions.stage)",
            (project,),
        )
        suggestions = []
        for row in rows:
            artifact = json.loads(row[0])
            if not any(
                link["stage"] == "requirements-input" and link["version"] == baseline
                for link in artifact["links"]
            ):
                continue
            for task in artifact["content"].get("tasks", []):
                if isinstance(task, dict) and task.get("id") and task.get("title"):
                    suggestions.append(
                        dict(
                            stage=artifact["stage"],
                            version=artifact["version"],
                            task=task["id"],
                            title=task["title"],
                            acceptance_criteria=task.get("acceptance_criteria", []),
                            source_references=task.get("requirement_refs", []),
                            created_at=artifact["created_at"],
                        )
                    )
        return suggestions

    def detail(self, project: str, identifier: str, actor: str, role: str) -> dict[str, Any]:
        with self.store.connect() as db:
            self.store.project(db, project, actor)
            item = self.item(db, project, identifier)
            return dict(
                item=item,
                editable_fields=self.fields(item, role),
                statuses=[item["status"], *sorted(ITEM_TRANSITIONS[item["status"]])],
                link_kinds=sorted(ITEM_LINKS[item["kind"]]),
                versions=[
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT data FROM work_item_versions WHERE project=? AND id=? "
                        "ORDER BY version DESC",
                        (project, identifier),
                    )
                ],
                annotations=[
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT data FROM work_item_annotations WHERE project=? AND item=? "
                        "ORDER BY rowid",
                        (project, identifier),
                    )
                ],
                suggestions=self.suggestions(
                    db, project, ProjectLifecycle.state(db, project)["baseline"]
                ),
            )

    def annotate(
        self, project: str, identifier: str, actor: str, role: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.store.project(db, project, actor)
            item = self.item(db, project, identifier)
            if item["version"] != payload["base_version"]:
                raise SDLCError("Record changed. Reload its detail before reviewing.")
            if payload["action"] != "comment":
                if not self.fields(item, role):
                    raise PermissionError("Your role cannot review suggestions for this record")
                source = payload["source"]
                suggestions = self.suggestions(
                    db, project, ProjectLifecycle.state(db, project)["baseline"]
                )
                if not source or not any(
                    all(suggestion[key] == source[key] for key in ("stage", "version", "task"))
                    for suggestion in suggestions
                ):
                    raise SDLCError(
                        "Suggestion source changed or is not current-baseline agent output"
                    )
            elif payload["source"] is not None:
                raise SDLCError("Comments do not contain suggestion decisions")
            data = dict(
                **payload,
                id=uuid4().hex,
                item=identifier,
                actor=actor,
                role=role,
                created_at=timestamp(),
                baseline=item["baseline"],
            )
            db.execute(
                "INSERT INTO work_item_annotations VALUES (?,?,?,?)",
                (data["id"], project, identifier, json.dumps(data)),
            )
            ProjectLifecycle.event(db, project, dict(data, action="record_" + payload["action"]))
            return data
