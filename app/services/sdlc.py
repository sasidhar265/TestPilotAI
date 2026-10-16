"""Project-scoped SDLC history with immutable revisions and optimistic concurrency."""

import json
import sqlite3
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

STAGES = ("planning", "requirements", "design", "development", "testing", "release", "operations")
REPOSITORY = Path(__file__).resolve().parents[2]


class SDLCError(ValueError):
    pass


class SDLCStore:
    def __init__(self, memory_path: Path) -> None:
        self.path = memory_path.resolve().parent / "sdlc.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS work_items (
                  id TEXT PRIMARY KEY, project TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS work_item_annotations (
                  id TEXT PRIMARY KEY, project TEXT NOT NULL, item TEXT NOT NULL,
                  data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS annotations_by_item
                  ON work_item_annotations(project,item);
                CREATE TABLE IF NOT EXISTS work_item_versions (
                  id TEXT NOT NULL, project TEXT NOT NULL, version INTEGER NOT NULL,
                  data TEXT NOT NULL, PRIMARY KEY(id,version));
                CREATE TABLE IF NOT EXISTS project_members (
                  project TEXT NOT NULL, username TEXT NOT NULL,
                  PRIMARY KEY(project, username));
                CREATE TABLE IF NOT EXISTS lifecycle (
                  project TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lifecycle_evidence (
                  id TEXT PRIMARY KEY, project TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lifecycle_events (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                  project TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS projects (
                  id TEXT PRIMARY KEY, owner TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (
                  project TEXT NOT NULL, stage TEXT NOT NULL, version INTEGER NOT NULL,
                  data TEXT NOT NULL, PRIMARY KEY(project, stage, version));
                CREATE TABLE IF NOT EXISTS runs (
                  id TEXT PRIMARY KEY, project TEXT NOT NULL, owner TEXT NOT NULL,
                  status TEXT NOT NULL, data TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_delivery ON runs(project)
                  WHERE status IN ('queued', 'running', 'cancelling');
                CREATE TABLE IF NOT EXISTS run_events (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                  run TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (
                  project TEXT NOT NULL, stage TEXT NOT NULL, version INTEGER NOT NULL,
                  data TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def project(db: sqlite3.Connection, identifier: str, owner: str) -> dict[str, Any]:
        row = db.execute(
            "SELECT data FROM projects WHERE id=? AND (owner=? OR EXISTS "
            "(SELECT 1 FROM project_members WHERE project=projects.id AND username=?))",
            (identifier, owner, owner),
        ).fetchone()
        if not row:
            raise SDLCError("Project not found")
        return dict(json.loads(row[0]))

    def create(self, name: str, owner: str) -> dict[str, Any]:
        data = dict(
            id=uuid4().hex, name=name, owner=owner, created_at=datetime.now(UTC).isoformat()
        )
        with self.connect() as db:
            db.execute("INSERT INTO projects VALUES (?,?,?)", (data["id"], owner, json.dumps(data)))
        return data

    def projects(self, owner: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT data FROM projects WHERE owner=? OR EXISTS "
                    "(SELECT 1 FROM project_members WHERE project=projects.id AND username=?) "
                    "ORDER BY rowid DESC",
                    (owner, owner),
                )
            ]

    def snapshot(self, identifier: str, owner: str) -> dict[str, Any]:
        with self.connect() as db:
            project = self.project(db, identifier, owner)
            artifacts = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT data FROM revisions WHERE project=? ORDER BY stage,version DESC",
                    (identifier,),
                )
            ]
            reviews = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT data FROM reviews WHERE project=? ORDER BY rowid", (identifier,)
                )
            ]
            runs = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT data FROM runs WHERE project=? ORDER BY rowid DESC", (identifier,)
                )
            ]
            return dict(project=project, artifacts=artifacts, reviews=reviews, runs=runs)

    def save(
        self,
        identifier: str,
        owner: str,
        stage: str,
        content: dict[str, Any],
        base_version: int,
        links: list[dict[str, Any]],
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        if stage not in (*STAGES, "workflow", "requirements-input"):
            raise SDLCError("Unknown lifecycle stage")
        if stage != "workflow" and not str(content.get("document", "")).strip():
            raise SDLCError("Enter a stage document before saving")
        if stage == "workflow" and (
            content.get("version") != 1 or not isinstance(content.get("state"), dict)
        ):
            raise SDLCError("Invalid testing workspace snapshot")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.project(db, identifier, owner)
            active = db.execute(
                "SELECT id FROM runs WHERE project=? AND status IN "
                "('queued','running','cancelling')",
                (identifier,),
            ).fetchone()
            if stage != "workflow" and active and active[0] != run_id:
                raise SDLCError("Stop the active delivery before changing lifecycle artifacts")
            current = db.execute(
                "SELECT COALESCE(MAX(version),0) FROM revisions WHERE project=? AND stage=?",
                (identifier, stage),
            ).fetchone()[0]
            if current != base_version:
                raise SDLCError("A newer version exists. Reload before saving your changes.")
            for link in links:
                found = db.execute(
                    "SELECT 1 FROM revisions WHERE project=? AND stage=? AND version=?",
                    (identifier, link["stage"], link["version"]),
                ).fetchone()
                if not found:
                    raise SDLCError("Linked artifact version does not exist in this project")
            data = dict(
                stage=stage,
                version=current + 1,
                content=content,
                links=links,
                author=owner,
                created_at=datetime.now(UTC).isoformat(),
            )
            db.execute(
                "INSERT INTO revisions VALUES (?,?,?,?)",
                (identifier, stage, current + 1, json.dumps(data)),
            )
            if stage == "requirements-input":
                from app.services.project_lifecycle import ProjectLifecycle

                ProjectLifecycle.source_changed(db, identifier, current + 1, owner)
            return data

    def review(
        self, identifier: str, owner: str, stage: str, version: int, decision: str, comment: str
    ) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.project(db, identifier, owner)
            latest = db.execute(
                "SELECT MAX(version) FROM revisions WHERE project=? AND stage=?",
                (identifier, stage),
            ).fetchone()[0]
            if latest != version:
                raise SDLCError("Review the latest artifact version")
            if stage == "workflow":
                raise SDLCError("Workflow snapshots are drafts, not approvable artifacts")
            data = dict(
                stage=stage,
                version=version,
                decision=decision,
                comment=comment,
                reviewer=owner,
                created_at=datetime.now(UTC).isoformat(),
            )
            db.execute(
                "INSERT INTO reviews VALUES (?,?,?,?)",
                (identifier, stage, version, json.dumps(data)),
            )
            return data

    def create_run(self, project: str, owner: str, mission: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = dict(
            id=uuid4().hex,
            project=project,
            owner=owner,
            mission=mission,
            status="queued",
            stage="planning",
            completed=[],
            artifacts={},
            created_at=datetime.now(UTC).isoformat(),
            updated_at=datetime.now(UTC).isoformat(),
            error=None,
            cancel_requested=False,
        )
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.project(db, project, owner)
            source_version = mission.get("requirements_version")
            if source_version is not None:
                latest_source = db.execute(
                    "SELECT MAX(version) FROM revisions "
                    "WHERE project=? AND stage='requirements-input'",
                    (project,),
                ).fetchone()[0]
                if latest_source != source_version:
                    raise SDLCError("Requirements changed. Save and start from the latest version.")
            try:
                db.execute(
                    "INSERT INTO runs VALUES (?,?,?,?,?)",
                    (data["id"], project, owner, "queued", json.dumps(data)),
                )
            except sqlite3.IntegrityError as error:
                raise SDLCError("This project already has an active delivery run") from error
        return data

    def run(self, identifier: str, owner: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT data FROM runs WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise SDLCError("Delivery run not found")
            data = dict(json.loads(row[0]))
            try:
                self.project(db, data["project"], owner)
            except SDLCError as error:
                raise SDLCError("Delivery run not found") from error
            data["events"] = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT data FROM run_events WHERE run=? ORDER BY sequence", (identifier,)
                )
            ]
            return data

    def update_run(self, identifier: str, owner: str, **changes: Any) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT data FROM runs WHERE id=? AND owner=?", (identifier, owner)
            ).fetchone()
            if not row:
                raise SDLCError("Delivery run not found")
            data = dict(json.loads(row[0]))
            data.update(changes, updated_at=datetime.now(UTC).isoformat())
            db.execute(
                "UPDATE runs SET status=?,data=? WHERE id=?",
                (data["status"], json.dumps(data), identifier),
            )
            return data

    def claim_run(self, identifier: str, owner: str) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT data FROM runs WHERE id=? AND owner=? AND status='queued'",
                (identifier, owner),
            ).fetchone()
            if not row:
                raise SDLCError("Run is already claimed or cannot be started")
            data = dict(json.loads(row[0]))
            data.update(status="running", updated_at=datetime.now(UTC).isoformat())
            db.execute(
                "UPDATE runs SET status='running',data=? WHERE id=?", (json.dumps(data), identifier)
            )
            return data

    def run_event(
        self, identifier: str, owner: str, stage: str, action: str, status: str, message: str
    ) -> None:
        event = dict(
            stage=stage,
            action=action,
            status=status,
            message=message,
            created_at=datetime.now(UTC).isoformat(),
        )
        with self.connect() as db:
            if not db.execute(
                "SELECT 1 FROM runs WHERE id=? AND owner=?", (identifier, owner)
            ).fetchone():
                raise SDLCError("Delivery run not found")
            db.execute(
                "INSERT INTO run_events(run,data) VALUES (?,?)", (identifier, json.dumps(event))
            )

    def resume_run(self, identifier: str, owner: str) -> dict[str, Any]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT data FROM runs WHERE id=? AND owner=?", (identifier, owner)
            ).fetchone()
            if not row:
                raise SDLCError("Delivery run not found")
            data = dict(json.loads(row[0]))
            if data["status"] not in {"blocked", "failed", "interrupted"}:
                raise SDLCError("Only blocked, failed or interrupted runs can resume")
            data.update(
                status="queued",
                cancel_requested=False,
                error=None,
                blocking_evidence={},
                updated_at=datetime.now(UTC).isoformat(),
            )
            try:
                db.execute(
                    "UPDATE runs SET status='queued',data=? WHERE id=?",
                    (json.dumps(data), identifier),
                )
            except sqlite3.IntegrityError as error:
                raise SDLCError("Another delivery run is active for this project") from error
            return data

    def recover_runs(self, owner: str) -> None:
        """Expired workers require an explicit new run; deployment is never replayed."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id,data FROM runs WHERE owner=? "
                "AND status IN ('queued','running','cancelling')",
                (owner,),
            ).fetchall()
            for identifier, raw in rows:
                data = json.loads(raw)
                elapsed = (
                    datetime.now(UTC) - datetime.fromisoformat(data["updated_at"])
                ).total_seconds()
                if elapsed > 120:
                    data.update(
                        status="interrupted",
                        error="Worker expired. Inspect deployment receipts before another run.",
                    )
                    db.execute(
                        "UPDATE runs SET status='interrupted',data=? WHERE id=?",
                        (json.dumps(data), identifier),
                    )


def repository_snapshot() -> dict[str, str]:
    """Read only the configured application checkout; never run user-supplied commands."""

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(REPOSITORY), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return result.stdout.strip()

    try:
        return dict(
            branch=git("branch", "--show-current"),
            commit=git("rev-parse", "HEAD"),
            changes=git("status", "--short"),
            commits=git("log", "-5", "--format=%h %s"),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SDLCError("The application repository is unavailable") from error
