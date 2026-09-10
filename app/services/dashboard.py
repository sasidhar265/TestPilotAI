"""Bounded workspace history, with live progress scoped to this server process."""

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import TestSuite

_ACTIVE: dict[str, dict[str, Any]] = {}


class DashboardStore:
    def __init__(self, memory_path: Path) -> None:
        self.path = memory_path.with_name("dashboard.db")

    def start(self, operation: str) -> str:
        identifier = uuid4().hex
        from app.observability import request_id_context

        _ACTIVE[identifier] = {
            "request_id": request_id_context.get(),
            "id": identifier,
            "operation": operation,
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
            "clock": time.monotonic(),
            "path": str(self.path),
        }
        return identifier

    def finish(self, identifier: str, status: str, details: dict[str, Any] | None = None) -> None:
        active = _ACTIVE.pop(identifier, None)
        if active is None:
            return
        record = {key: value for key, value in active.items() if key not in {"clock", "path"}}
        record.update(
            status=status,
            finished_at=datetime.now(UTC).isoformat(),
            duration_ms=round((time.monotonic() - active["clock"]) * 1000),
            details=details or {},
        )
        from app.observability import lifecycle_events

        if record["request_id"] != "-":
            record["events"] = lifecycle_events.read(record["request_id"], 0).get("events", [])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS work_history "
                "(id INTEGER PRIMARY KEY, record TEXT NOT NULL)"
            )
            connection.execute("INSERT INTO work_history(record) VALUES (?)", (json.dumps(record),))
            connection.execute(
                "DELETE FROM work_history WHERE id NOT IN "
                "(SELECT id FROM work_history ORDER BY id DESC LIMIT 200)"
            )

    def snapshot(self) -> dict[str, Any]:
        history = []
        if self.path.exists():
            with closing(sqlite3.connect(self.path)) as connection:
                history = [
                    json.loads(row[0])
                    for row in connection.execute(
                        "SELECT record FROM work_history ORDER BY id DESC LIMIT 200"
                    )
                ]
        active = [
            {key: value for key, value in item.items() if key not in {"clock", "path"}}
            | {"duration_ms": round((time.monotonic() - item["clock"]) * 1000)}
            for item in _ACTIVE.values()
            if item["path"] == str(self.path)
        ]
        from app.observability import lifecycle_events

        for item in active:
            if item["request_id"] != "-":
                events = lifecycle_events.read(item["request_id"], 0).get("events", [])
                if isinstance(events, list) and events:
                    item["events"] = events
                    item["progress"] = events[-1]["summary"]
        return {
            "active": active,
            "history": history,
            "scope": "Last 200 completed workspace actions; active work on this server process.",
        }


def suite_details(suite: TestSuite, validated: bool) -> dict[str, Any]:
    return {
        "suite_key": hashlib.sha256(
            json.dumps(
                {
                    "feature": suite.feature_name,
                    "cases": [case.model_dump(mode="json") for case in suite.test_cases],
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        "feature": suite.feature_name,
        "validated": validated,
        "source": suite.generation_source.value,
        "cases": [
            {
                "id": case.id,
                "category": case.category.value,
                "mode": case.execution_mode.value,
                "priority": case.priority,
                "requirements": case.acceptance_criteria_covered,
                "execution": "not_run",
            }
            for case in suite.test_cases
        ],
    }
