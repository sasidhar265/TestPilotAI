"""Persist validated C# bundles and retrieve exact scenario implementation knowledge."""

import hashlib
import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING

from app.memory import OrganizationalMemory
from app.models import TestSuite

if TYPE_CHECKING:
    from app.agents.reqnroll_step_definition_agent import StepDefinitionArtifact

logger = logging.getLogger(__name__)


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class ReqnRollMemory:
    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled

    @staticmethod
    def identity(suite: TestSuite, profile: str, instructions: str) -> tuple[str, list[str]]:
        # Preserve case and whitespace in literals, Examples, fixtures and expected results.
        # IDs and display metadata do not change the implementation contract.
        scenarios = sorted(
            {
                _digest(
                    case.model_dump(
                        mode="json",
                        exclude={"id", "title", "category", "priority", "feasibility_reason"},
                    )
                )
                for case in suite.test_cases
            }
        )
        templates = Path(__file__).resolve().parents[1] / "templates" / "reqnroll"
        scope = _digest(
            {
                "version": 1,
                "profile": profile,
                "instructions": instructions,
                "feature": suite.feature_name,
                "assumptions": suite.assumptions,
                "coverage_notes": suite.coverage_notes,
                "templates": {p.name: p.read_text() for p in sorted(templates.glob("*.cs"))},
            }
        )
        return scope, scenarios

    def candidates(self, scope: str, scenarios: list[str]) -> list[tuple[bool, str]]:
        if not self.enabled or not self.path.exists():
            return []
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT scenarios_json, artifact_json FROM reqnroll_memory WHERE scope = ?",
                    (scope,),
                ).fetchall()
            wanted = set(scenarios)
            ranked = []
            for keys, artifact in rows:
                stored = set(json.loads(keys))
                overlap = len(wanted & stored)
                if overlap:
                    ranked.append((stored == wanted, overlap, artifact))
            ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
            return [(exact, artifact) for exact, _, artifact in ranked[:3]]
        except (sqlite3.Error, OSError, ValueError, TypeError):
            logger.warning("reqnroll_memory_read_failed")
            return []

    def put(self, scope: str, scenarios: list[str], artifact: "StepDefinitionArtifact") -> None:
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            OrganizationalMemory._restrict_permissions(self.path.parent, 0o700)
            with closing(self._connect()) as connection:
                connection.execute(
                    "INSERT INTO reqnroll_memory "
                    "(memory_key, scope, scenarios_json, artifact_json) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(memory_key) DO UPDATE SET "
                    "artifact_json = excluded.artifact_json",
                    (
                        _digest([scope, scenarios]),
                        scope,
                        json.dumps(scenarios),
                        artifact.model_dump_json(),
                    ),
                )
                connection.commit()
        except (sqlite3.Error, OSError):
            logger.warning("reqnroll_memory_write_failed")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        OrganizationalMemory._restrict_permissions(self.path, 0o600)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS reqnroll_memory (memory_key TEXT PRIMARY KEY, "
            "scope TEXT NOT NULL, scenarios_json TEXT NOT NULL, artifact_json TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS reqnroll_memory_scope ON reqnroll_memory(scope)"
        )
        return connection
