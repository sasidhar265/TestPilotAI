"""Transactional STLC records. Snapshots and execution attempts are never overwritten."""

import hashlib
import io
import json
import re
import sqlite3
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from app.audit_integrity import append_event, initialize_audit, verify_audit
from app.automation_layout import validate_layout_paths
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


class LifecycleError(ValueError):
    pass


class LifecycleStore:
    def __init__(self, memory_path: Path) -> None:
        self.path = memory_path.resolve().parent / "stlc.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, "
                "kind TEXT NOT NULL, data TEXT NOT NULL)"
            )
            db.execute("CREATE INDEX IF NOT EXISTS record_kind ON records(kind)")
            db.execute(
                "CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
                "record_id TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL, "
                "comment TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            initialize_audit(db)
            verify_audit(db)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def all(db: sqlite3.Connection, kind: str) -> list[dict[str, Any]]:
        return [
            json.loads(row[0])
            for row in db.execute("SELECT data FROM records WHERE kind=? ORDER BY rowid", (kind,))
        ]

    @staticmethod
    def get(db: sqlite3.Connection, identifier: str, kind: str) -> dict[str, Any]:
        row = db.execute(
            "SELECT data FROM records WHERE id=? AND kind=?", (identifier, kind)
        ).fetchone()
        if not row:
            raise LifecycleError(f"Unknown {kind} record")
        return dict(json.loads(row[0]))

    @staticmethod
    def put(db: sqlite3.Connection, kind: str, data: dict[str, Any]) -> dict[str, Any]:
        db.execute(
            "INSERT INTO records VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (data["id"], kind, json.dumps(data)),
        )
        return data

    @staticmethod
    def event(
        db: sqlite3.Connection, identifier: str, action: str, actor: str, comment: str
    ) -> None:
        append_event(
            db,
            (identifier, action, actor, comment, datetime.now(UTC).isoformat()),
        )

    def create(
        self, db: sqlite3.Connection, kind: str, data: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        data = data | {
            "id": uuid4().hex,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": actor,
        }
        self.put(db, kind, data)
        self.event(db, data["id"], "created", actor, "")
        return data

    def requirement(self, payload: RequirementInput, actor: str) -> dict[str, Any]:
        with self.transaction() as db:
            previous = [
                r
                for r in self.all(db, "requirement")
                if r["project"] == payload.project and r["key"] == payload.key
            ]
            version = max((r["version"] for r in previous), default=0)
            if payload.expected_version != version:
                raise LifecycleError("Requirement changed; reload the latest version before saving")
            data = payload.model_dump(exclude={"expected_version"}) | {
                "version": version + 1,
                "status": "draft",
            }
            data["quality_flags"] = (
                [] if payload.acceptance_criteria else ["Acceptance criteria are missing"]
            )
            if any(
                re.search(r"\b(appropriate|user.friendly|as expected|etc)\b", value, re.I)
                for value in payload.acceptance_criteria
            ):
                data["quality_flags"].append("Review potentially ambiguous acceptance criteria")
            return self.create(db, "requirement", data, actor)

    def review(
        self, kind: str, identifier: str, payload: ReviewInput, actor: str
    ) -> dict[str, Any]:
        if kind not in {"requirement", "baseline", "suite"}:
            raise LifecycleError("Unsupported review record")
        with self.transaction() as db:
            item = self.get(db, identifier, kind)
            transitions = {
                ("draft", "submit"): "in-review",
                ("in-review", "approve"): "approved",
                ("in-review", "reject"): "draft",
            }
            if payload.action != "comment":
                status = transitions.get((item["status"], payload.action))
                if not status:
                    raise LifecycleError("Invalid review transition")
                if kind == "requirement":
                    newer = [
                        r
                        for r in self.all(db, kind)
                        if r["project"] == item["project"]
                        and r["key"] == item["key"]
                        and r["version"] > item["version"]
                    ]
                    if newer:
                        raise LifecycleError("Only the latest requirement version can be reviewed")
                    if payload.action == "approve" and item["quality_flags"]:
                        raise LifecycleError(
                            "Resolve requirement quality flags in a new version before approval"
                        )
                if payload.action == "approve" and kind in {"baseline", "suite"}:
                    baseline = (
                        item
                        if kind == "baseline"
                        else self.get(db, item["baseline_id"], "baseline")
                    )
                    self.assert_current_baseline(db, baseline)
                    if kind == "suite" and baseline["status"] != "approved":
                        raise LifecycleError("Approve the baseline first")
                item["status"] = status
                if status == "approved":
                    item["approved_by"] = actor
                    item["approved_at"] = datetime.now(UTC).isoformat()
                    if kind == "requirement":
                        for old in self.all(db, kind):
                            if (
                                old["project"] == item["project"]
                                and old["key"] == item["key"]
                                and old["status"] == "approved"
                            ):
                                old["status"] = "superseded"
                                self.put(db, kind, old)
                                self.event(db, old["id"], "superseded", actor, item["id"])
                self.put(db, kind, item)
            self.event(db, identifier, payload.action, actor, payload.comment)
            return item

    def assert_current_baseline(self, db: sqlite3.Connection, baseline: dict[str, Any]) -> None:
        requirements = self.all(db, "requirement")
        for snapshot in baseline["requirements"]:
            latest = max(
                (
                    r
                    for r in requirements
                    if r["project"] == baseline["project"] and r["key"] == snapshot["key"]
                ),
                key=lambda r: r["version"],
            )
            if latest["id"] != snapshot["id"] or latest["status"] != "approved":
                raise LifecycleError(
                    "Baseline contains changed or unapproved requirements; "
                    "create and review a new baseline"
                )

    def baseline(self, payload: BaselineInput, actor: str) -> dict[str, Any]:
        with self.transaction() as db:
            requirements = [self.get(db, key, "requirement") for key in payload.requirement_ids]
            if len({r["key"] for r in requirements}) != len(requirements):
                raise LifecycleError("Select one version per requirement")
            if any(
                r["project"] != payload.project or r["status"] != "approved" for r in requirements
            ):
                raise LifecycleError(
                    "Baseline requires approved requirements from the same project"
                )
            data = {
                "project": payload.project,
                "name": payload.name,
                "requirements": requirements,
                "status": "draft",
            }
            self.assert_current_baseline(db, data)
            return self.create(db, "baseline", data, actor)

    def suite(self, payload: SuiteVersionInput, actor: str) -> dict[str, Any]:
        with self.transaction() as db:
            baseline = self.get(db, payload.baseline_id, "baseline")
            if baseline["status"] != "approved":
                raise LifecycleError("Approve the baseline before saving a suite version")
            self.assert_current_baseline(db, baseline)
            case_ids = {c.id for c in payload.suite.test_cases}
            keys = {r["key"] for r in baseline["requirements"]}
            if len(case_ids) != len(payload.suite.test_cases):
                raise LifecycleError("Test case IDs must be unique")
            if set(payload.mappings) != case_ids or any(
                not values or not set(values) <= keys for values in payload.mappings.values()
            ):
                raise LifecycleError("Map every test case to known baseline requirement keys")
            data = payload.model_dump(mode="json") | {
                "project": baseline["project"],
                "status": "draft",
            }
            data["mappings"] = {
                key: sorted(set(values)) for key, values in payload.mappings.items()
            }
            data["content_hash"] = hashlib.sha256(
                json.dumps(data, sort_keys=True).encode()
            ).hexdigest()
            return self.create(db, "suite", data, actor)

    def cycle(self, payload: CycleInput, actor: str) -> dict[str, Any]:
        with self.transaction() as db:
            suite = self.get(db, payload.suite_id, "suite")
            baseline = self.get(db, suite["baseline_id"], "baseline")
            if suite["status"] != "approved" or baseline["status"] != "approved":
                raise LifecycleError("Execution requires an approved suite and baseline")
            self.assert_current_baseline(db, baseline)
            if set(payload.assignments) != set(suite["mappings"]):
                raise LifecycleError("Assign every test case before creating the cycle")
            return self.create(
                db,
                "cycle",
                payload.model_dump() | {"project": suite["project"], "baseline_id": baseline["id"]},
                actor,
            )

    def attempt(
        self,
        db: sqlite3.Connection,
        cycle: dict[str, Any],
        payload: AttemptInput,
        actor: str,
        source: str,
        run_key: str | None = None,
    ) -> dict[str, Any]:
        suite = self.get(db, cycle["suite_id"], "suite")
        test = next((c for c in suite["suite"]["test_cases"] if c["id"] == payload.case_id), None)
        if test is None:
            raise LifecycleError("Result case ID does not belong to this cycle")
        numbers = [step.step for step in payload.steps]
        if len(numbers) != len(set(numbers)) or any(n > len(test["steps"]) for n in numbers):
            raise LifecycleError("Invalid or duplicate step evidence")
        if source == "manual" and payload.status in {"passed", "failed"}:
            if set(numbers) != set(range(1, len(test["steps"]) + 1)):
                raise LifecycleError("Record each step before completing a manual attempt")
            if payload.status == "passed" and any(s.status != "passed" for s in payload.steps):
                raise LifecycleError("A passed attempt requires all steps to pass")
            if payload.status == "failed" and not any(s.status == "failed" for s in payload.steps):
                raise LifecycleError("A failed attempt requires a failed step")
        if payload.retest_of:
            prior = self.get(db, payload.retest_of, "attempt")
            if (
                self.get(db, prior["cycle_id"], "cycle")["suite_id"] != cycle["suite_id"]
                or prior["case_id"] != payload.case_id
                or prior["status"] not in {"failed", "blocked"}
            ):
                raise LifecycleError(
                    "Retest must reference a failed or blocked attempt "
                    "for this case and suite version"
                )
        return self.create(
            db,
            "attempt",
            payload.model_dump(mode="json")
            | {"cycle_id": cycle["id"], "source": source, "run_key": run_key},
            actor,
        )

    def record_attempt(self, cycle_id: str, payload: AttemptInput, actor: str) -> dict[str, Any]:
        with self.transaction() as db:
            return self.attempt(db, self.get(db, cycle_id, "cycle"), payload, actor, "manual")

    def import_results(
        self, cycle_id: str, payload: ImportInput, actor: str
    ) -> list[dict[str, Any]]:
        with self.transaction() as db:
            cycle = self.get(db, cycle_id, "cycle")
            if payload.build != cycle["build"] or payload.environment != cycle["environment"]:
                raise LifecycleError("Result build and environment must match the cycle")
            digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
            previous = [
                r
                for r in self.all(db, "import")
                if r["cycle_id"] == cycle_id and r["run_key"] == payload.run_key
            ]
            if previous:
                if previous[0]["digest"] != digest:
                    raise LifecycleError("Run key already used for different results")
                return [
                    r
                    for r in self.all(db, "attempt")
                    if r["cycle_id"] == cycle_id and r["run_key"] == payload.run_key
                ]
            attempts = [
                self.attempt(db, cycle, item, actor, "automation-import", payload.run_key)
                for item in payload.results
            ]
            self.create(
                db,
                "import",
                {"cycle_id": cycle_id, "run_key": payload.run_key, "digest": digest},
                actor,
            )
            return attempts

    def defect(self, payload: DefectInput, actor: str) -> dict[str, Any]:
        with self.transaction() as db:
            attempt = self.get(db, payload.attempt_id, "attempt")
            if attempt["status"] != "failed":
                raise LifecycleError("Defects must link to a failed execution attempt")
            return self.create(
                db,
                "defect",
                payload.model_dump()
                | {
                    "cycle_id": attempt["cycle_id"],
                    "case_id": attempt["case_id"],
                    "status": "open",
                },
                actor,
            )

    def update_defect(self, identifier: str, payload: DefectUpdate, actor: str) -> dict[str, Any]:
        with self.transaction() as db:
            defect = self.get(db, identifier, "defect")
            if payload.status == "closed":
                original_cycle = self.get(db, defect["cycle_id"], "cycle")
                compatible = {
                    c["id"]
                    for c in self.all(db, "cycle")
                    if c["suite_id"] == original_cycle["suite_id"]
                }
                attempts = [
                    a
                    for a in self.all(db, "attempt")
                    if a["cycle_id"] in compatible and a["case_id"] == defect["case_id"]
                ]
                if (
                    not attempts
                    or attempts[-1]["status"] != "passed"
                    or not any(
                        a["status"] == "passed" and a["retest_of"] == defect["attempt_id"]
                        for a in attempts
                    )
                ):
                    raise LifecycleError(
                        "Closing a defect requires a passing retest of its failed attempt "
                        "and no later failure"
                    )
            defect["status"] = payload.status
            if payload.jira_key:
                defect["jira_key"] = payload.jira_key
                defect["jira_publish_pending"] = False
            self.put(db, "defect", defect)
            self.event(db, identifier, payload.status, actor, payload.comment)
            return defect

    def snapshot(self) -> dict[str, Any]:
        with self.transaction() as db:
            data = {
                kind + "s": self.all(db, kind)
                for kind in ("requirement", "baseline", "suite", "cycle", "attempt", "defect")
            }
            data["audit"] = [
                dict(
                    zip(("record_id", "action", "actor", "comment", "created_at"), row, strict=True)
                )
                for row in db.execute(
                    "SELECT record_id,action,actor,comment,created_at "
                    "FROM audit ORDER BY sequence DESC LIMIT 500"
                )
            ]
            data["impacts"] = []
            for suite in data["suites"]:
                baseline = self.get(db, suite["baseline_id"], "baseline")
                for requirement in baseline["requirements"]:
                    latest = max(
                        (
                            r
                            for r in data["requirements"]
                            if r["project"] == baseline["project"]
                            and r["key"] == requirement["key"]
                        ),
                        key=lambda r: r["version"],
                    )
                    if latest["id"] != requirement["id"]:
                        cases = [
                            key
                            for key, values in suite["mappings"].items()
                            if requirement["key"] in values
                        ]
                        data["impacts"].append(
                            {
                                "suite_id": suite["id"],
                                "requirement": requirement["key"],
                                "from_version": requirement["version"],
                                "to_version": latest["version"],
                                "case_ids": cases,
                                "changed_fields": [
                                    field
                                    for field in (
                                        "title",
                                        "description",
                                        "acceptance_criteria",
                                        "owner",
                                        "source",
                                    )
                                    if requirement[field] != latest[field]
                                ],
                                "cycle_ids": [
                                    c["id"] for c in data["cycles"] if c["suite_id"] == suite["id"]
                                ],
                            }
                        )
            return data

    def report(self, cycle_id: str) -> dict[str, Any]:
        data = self.snapshot()
        cycle = next((c for c in data["cycles"] if c["id"] == cycle_id), None)
        if not cycle:
            raise LifecycleError("Unknown cycle")
        suite = next(s for s in data["suites"] if s["id"] == cycle["suite_id"])
        baseline = next(b for b in data["baselines"] if b["id"] == cycle["baseline_id"])
        attempts = [a for a in data["attempts"] if a["cycle_id"] == cycle_id]
        latest = {a["case_id"]: a for a in attempts}
        counts = {
            status: sum(
                latest.get(key, {}).get("status", "not-run") == status for key in suite["mappings"]
            )
            for status in ("passed", "failed", "blocked", "not-run")
        }
        matrix = []
        for requirement in baseline["requirements"]:
            ids = [key for key, values in suite["mappings"].items() if requirement["key"] in values]
            matrix.append(
                {
                    "requirement": requirement["key"],
                    "version": requirement["version"],
                    "case_ids": ids,
                    "passed": bool(ids)
                    and all(latest.get(key, {}).get("status") == "passed" for key in ids),
                }
            )
        executed = counts["passed"] + counts["failed"]
        return {
            "cycle": cycle,
            "total": len(suite["mappings"]),
            "counts": counts,
            "executed": executed,
            "pass_rate": round(counts["passed"] * 100 / executed, 2) if executed else None,
            "matrix": matrix,
            "latest": latest,
            "attempts": attempts,
            "defects": [d for d in data["defects"] if d["cycle_id"] == cycle_id],
            "impacts": [i for i in data["impacts"] if i["suite_id"] == suite["id"]],
        }

    def pack(self, cycle_id: str, payload: PackInput, actor: str) -> bytes:
        with self.transaction() as db:
            cycle = self.get(db, cycle_id, "cycle")
            suite = self.get(db, cycle["suite_id"], "suite")
            files = payload.files
            try:
                validate_layout_paths(files)
            except ValueError as error:
                raise LifecycleError(str(error)) from error
            for name in files:
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in name
                    or ":" in name
                    or str(path) != name
                    or name in {"manifest.json", "results.json"}
                ):
                    raise LifecycleError("Unsafe pack file path")
            if sum(len(content.encode()) for content in files.values()) > 5_000_000:
                raise LifecycleError("Pack exceeds 5 MB")
            if payload.project_path not in files or not payload.project_path.endswith(".csproj"):
                raise LifecycleError("Select the C# test project included in the pack")
            automated = {
                c["id"] for c in suite["suite"]["test_cases"] if c["execution_mode"] == "automation"
            }
            if set(payload.test_mappings.values()) != automated:
                raise LifecycleError("Map every automated case to its exact TRX test name")
            manifest = {
                "cycle_id": cycle_id,
                "suite_hash": suite["content_hash"],
                "build": cycle["build"],
                "environment": cycle["environment"],
                "project_path": payload.project_path,
                "test_mappings": payload.test_mappings,
                "files": {
                    name: hashlib.sha256(content.encode()).hexdigest()
                    for name, content in files.items()
                },
                "reviewed_by": actor,
                "review_comment": payload.review_comment,
            }
            receipt = self.create(db, "pack", manifest, actor)
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, content in files.items():
                    archive.writestr(name, content)
                archive.writestr("manifest.json", json.dumps(receipt, indent=2))
            return output.getvalue()
