import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.models import GenerateRequest, GenerationSource, TestSuite


class OrganizationalMemory:
    """Repository-local, exact-match memory for validated test suites."""

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled

    @staticmethod
    def key_for(request: GenerateRequest) -> str:
        normalized = {
            "description": " ".join(request.description.casefold().split()),
            "additional_context": " ".join(request.additional_context.casefold().split()),
            "output_format": request.output_format.value,
            "generation_target": request.generation_target.value,
            # Bump when generation policy changes would make approved cached suites stale.
            "schema_version": 6,
        }
        value = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def get(self, request: GenerateRequest) -> TestSuite | None:
        if not self.enabled or not self.path.exists():
            return None
        key = self.key_for(request)
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT suite_json FROM test_suite_memory WHERE memory_key = ?", (key,)
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE test_suite_memory SET last_accessed_at = ?, "
                "access_count = access_count + 1 "
                "WHERE memory_key = ?",
                (self._now(), key),
            )
            connection.commit()
        suite = TestSuite.model_validate_json(row[0])
        return suite.model_copy(
            update={
                "generation_source": GenerationSource.ORGANIZATIONAL_MEMORY,
                "memory_key": key[:12],
            }
        )

    def put(self, request: GenerateRequest, suite: TestSuite) -> TestSuite:
        if not self.enabled:
            return suite
        self.path.parent.mkdir(parents=True, exist_ok=True)
        key = self.key_for(request)
        stored = suite.model_copy(
            update={
                "generation_source": GenerationSource.COPILOT,
                "memory_key": key[:12],
            }
        )
        now = self._now()
        with closing(self._connect()) as connection:
            connection.execute(
                """INSERT INTO test_suite_memory
                   (memory_key, suite_json, created_at, last_accessed_at, access_count)
                   VALUES (?, ?, ?, ?, 0)
                   ON CONFLICT(memory_key) DO UPDATE SET
                     suite_json = excluded.suite_json,
                     created_at = excluded.created_at,
                     last_accessed_at = excluded.last_accessed_at""",
                (key, stored.model_dump_json(), now, now),
            )
            connection.commit()
        return stored

    def count(self) -> int:
        if not self.enabled or not self.path.exists():
            return 0
        with closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM test_suite_memory").fetchone()[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute(
            """CREATE TABLE IF NOT EXISTS test_suite_memory (
                 memory_key TEXT PRIMARY KEY,
                 suite_json TEXT NOT NULL,
                 created_at TEXT NOT NULL,
                 last_accessed_at TEXT NOT NULL,
                 access_count INTEGER NOT NULL DEFAULT 0
               )"""
        )
        return connection

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
