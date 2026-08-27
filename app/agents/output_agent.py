"""Durable storage and retrieval for approved converted test knowledge."""

import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.agents.context_converter_agent import ConvertedArtifact
from app.agents.roles import AgentKind, FunctionalAgentDescriptor
from app.models import ExportFormat, GenerateRequest, TestSuite

_WORDS = re.compile(r"[a-z0-9]{3,}")


class OutputAgent:
    descriptor = FunctionalAgentDescriptor(
        id="output-agent",
        name="Output Agent",
        kind=AgentKind.OUTPUT,
        purpose="Store approved converted artifacts and provide reusable organizational knowledge.",
        runtime="local-sqlite",
        capabilities=(
            "feature-file-storage",
            "scenario-storage",
            "artifact-storage",
            "knowledge-source",
            "relevant-example-retrieval",
        ),
        instruction_file=".github/agents/output.agent.md",
    )

    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled

    def store(
        self, suite: TestSuite, output_format: ExportFormat, artifact: ConvertedArtifact
    ) -> str | None:
        if not self.enabled:
            return None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(artifact.content).hexdigest()
        with closing(self._connect()) as connection:
            connection.execute(
                """INSERT INTO converted_outputs
                   (artifact_id, filename, output_format, media_type, content, suite_json,
                    search_text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(artifact_id) DO NOTHING""",
                (
                    digest,
                    artifact.filename,
                    output_format.value,
                    artifact.media_type,
                    artifact.content,
                    suite.model_dump_json(),
                    self._search_text(suite),
                    datetime.now(UTC).isoformat(),
                ),
            )
            for case in suite.test_cases:
                connection.execute(
                    """INSERT INTO output_scenarios
                       (artifact_id, case_id, title, execution_mode, gherkin,
                        requirements_json, scenario_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(artifact_id, case_id) DO UPDATE SET
                         title = excluded.title,
                         execution_mode = excluded.execution_mode,
                         gherkin = excluded.gherkin,
                         requirements_json = excluded.requirements_json,
                         scenario_json = excluded.scenario_json""",
                    (
                        digest,
                        case.id,
                        case.title,
                        case.execution_mode.value,
                        case.gherkin or "",
                        json.dumps(case.acceptance_criteria_covered, ensure_ascii=False),
                        case.model_dump_json(),
                    ),
                )
            connection.commit()
        return digest[:12]

    def knowledge_for(self, request: GenerateRequest, limit: int = 2) -> str:
        """Return bounded relevant approved examples; this is retrieval, not model training."""
        if not self.enabled or not self.path.exists():
            return ""
        query = self._tokens(request.description + " " + request.additional_context)
        if not query:
            return ""
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT suite_json, search_text FROM converted_outputs ORDER BY created_at DESC"
            ).fetchall()
        ranked: list[tuple[float, TestSuite]] = []
        for suite_json, search_text in rows:
            candidate = self._tokens(search_text)
            score = len(query & candidate) / len(query | candidate) if candidate else 0
            if score > 0:
                ranked.append((score, TestSuite.model_validate_json(suite_json)))
        examples = [
            suite for _, suite in sorted(ranked, key=lambda item: item[0], reverse=True)[:limit]
        ]
        if not examples:
            return ""
        payload = [
            {
                "feature": suite.feature_name,
                "approved_cases": [
                    {
                        "title": case.title,
                        "objective": case.objective,
                        "requirements": case.acceptance_criteria_covered,
                    }
                    for case in suite.test_cases[:5]
                ],
            }
            for suite in examples
        ]
        return (
            "APPROVED ORGANIZATIONAL KNOWLEDGE (reference patterns only; current requirements "
            "take precedence)\n" + json.dumps(payload, ensure_ascii=False)
        )[:4000]

    def count(self) -> int:
        if not self.enabled or not self.path.exists():
            return 0
        with closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM converted_outputs").fetchone()[0])

    def scenario_count(self) -> int:
        if not self.enabled or not self.path.exists():
            return 0
        with closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM output_scenarios").fetchone()[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute(
            """CREATE TABLE IF NOT EXISTS converted_outputs (
                 artifact_id TEXT PRIMARY KEY,
                 filename TEXT NOT NULL,
                 output_format TEXT NOT NULL,
                 media_type TEXT NOT NULL,
                 content BLOB NOT NULL,
                 suite_json TEXT NOT NULL,
                 search_text TEXT NOT NULL,
                 created_at TEXT NOT NULL
               )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS output_scenarios (
                 artifact_id TEXT NOT NULL,
                 case_id TEXT NOT NULL,
                 title TEXT NOT NULL,
                 execution_mode TEXT NOT NULL,
                 gherkin TEXT NOT NULL,
                 requirements_json TEXT NOT NULL,
                 scenario_json TEXT NOT NULL,
                 PRIMARY KEY (artifact_id, case_id),
                 FOREIGN KEY (artifact_id) REFERENCES converted_outputs(artifact_id)
               )"""
        )
        return connection

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return set(_WORDS.findall(value.casefold()))

    @staticmethod
    def _search_text(suite: TestSuite) -> str:
        values = [suite.feature_name]
        for case in suite.test_cases:
            values.extend(
                [case.title, case.objective, *case.tags, *case.acceptance_criteria_covered]
            )
        return " ".join(values)
