"""Storage confidentiality, retention, deletion, migration, and transaction checks."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from test_memory import suite

from app.agents.context_converter_agent import ConvertedArtifact
from app.agents.output_agent import OutputAgent
from app.agents.reqnroll_memory import ReqnRollMemory
from app.config import Settings
from app.memory import OrganizationalMemory
from app.memory_admin import erase, migrate
from app.models import ExportFormat, GenerateRequest
from app.protected_memory import MAGIC, MemoryProtection, MemoryProtectionError


@pytest.fixture
def protected(tmp_path):
    return tmp_path / "knowledge.db", MemoryProtection(Fernet.generate_key().decode(), 1)


def populate(path, protection):
    memory = OrganizationalMemory(path, protection=protection)
    request = GenerateRequest(description="Synthetic confidential finance requirement")
    result = suite()
    result.feature_name = "Synthetic confidential customer requirement"
    memory.put(request, result)
    memory.save_review(request, result, "TC-001 synthetic confidential review")
    memory.remember_workflow("workflow", '{"stories": ["synthetic confidential story"]}')
    output = OutputAgent(path, protection=protection)
    output.store(
        result,
        ExportFormat.JSON,
        ConvertedArtifact(
            b"synthetic confidential export", "confidential.json", "application/json"
        ),
    )
    artifact = Mock()
    artifact.model_dump_json.return_value = '{"source": "synthetic confidential C#"}'
    ReqnRollMemory(path, protection=protection).put("scope", ["scenario"], artifact)
    return memory, output, request


def test_all_memory_content_is_encrypted_and_reopens(protected):
    path, protection = protected
    memory, output, request = populate(path, protection)
    assert path.read_bytes().startswith(MAGIC)
    for file in path.parent.iterdir():
        assert b"confidential" not in file.read_bytes()
        assert b"SQLite format" not in file.read_bytes()
    assert memory.get(request).feature_name == "Synthetic confidential customer requirement"
    assert "confidential review" in memory.with_reviews(request).additional_context
    assert "confidential story" in memory.recall_workflow("workflow")
    assert output.count() == output.scenario_count() == 1
    assert ReqnRollMemory(path, protection=protection).candidates("scope", ["scenario"])
    assert path.stat().st_mode & 0o077 == 0
    assert not path.with_name(path.name + "-wal").exists()


@pytest.mark.parametrize("failure", ["missing-key", "wrong-key", "tampered"])
def test_unreadable_memory_is_not_overwritten(protected, failure):
    path, protection = protected
    populate(path, protection)
    if failure == "missing-key":
        protection = MemoryProtection("")
    elif failure == "wrong-key":
        protection = MemoryProtection(Fernet.generate_key().decode())
    else:
        payload = bytearray(path.read_bytes())
        payload[-8] ^= 1
        path.write_bytes(payload)
    original = path.read_bytes()
    with pytest.raises(MemoryProtectionError):
        protection.connect(path)
    assert path.read_bytes() == original


def test_plaintext_is_refused_and_migrated_without_changing_source(protected):
    path, protection = protected
    legacy = path.with_name("legacy.db")
    with sqlite3.connect(legacy) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE workflow_memory (memory_key TEXT PRIMARY KEY, artifact_json TEXT)")
        db.execute("INSERT INTO workflow_memory VALUES ('old', 'confidential legacy story')")
    original = legacy.read_bytes()
    with pytest.raises(MemoryProtectionError, match="Plaintext"):
        protection.connect(legacy)
    migrate(legacy, path, protection)
    assert legacy.read_bytes() == original
    assert OrganizationalMemory(path, protection=protection).recall_workflow("old") == (
        "confidential legacy story"
    )
    with pytest.raises(MemoryProtectionError, match="already exists"):
        migrate(legacy, path, protection)


def test_expiry_covers_all_caches_and_reads_do_not_extend_retention(protected, monkeypatch):
    path, protection = protected
    now = [1800000000.0]
    monkeypatch.setattr("app.protected_memory.time.time", lambda: now[0])
    memory, output, request = populate(path, protection)
    now[0] += 86399
    assert memory.get(request) is not None
    assert output.count() == 1
    now[0] += 2
    assert memory.get(request) is None
    assert memory.entries() == []
    assert memory.with_reviews(request) == request
    assert memory.recall_workflow("workflow") is None
    assert output.count() == output.scenario_count() == 0
    assert ReqnRollMemory(path, protection=protection).candidates("scope", ["scenario"]) == []
    with closing(protection.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM review_feedback").fetchone()[0] == 0


def test_erase_removes_every_memory_copy(protected):
    path, protection = protected
    memory, output, request = populate(path, protection)
    erase(path, protection)
    assert memory.count() == output.count() == output.scenario_count() == 0
    assert memory.with_reviews(request) == request
    assert memory.recall_workflow("workflow") is None
    assert b"confidential" not in protection.read(path)


def test_parallel_writers_do_not_lose_updates(protected):
    path, protection = protected

    def write(number):
        OrganizationalMemory(path, protection=protection).remember_workflow(
            str(number), str(number)
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, range(12)))
    memory = OrganizationalMemory(path, protection=protection)
    assert [memory.recall_workflow(str(i)) for i in range(12)] == [str(i) for i in range(12)]


def test_close_rolls_back_uncommitted_content(protected):
    path, protection = protected
    memory = OrganizationalMemory(path, protection=protection)
    memory.remember_workflow("committed", "kept")
    with closing(protection.connect(path)) as db:
        db.execute(
            "INSERT INTO workflow_memory (memory_key, artifact_json) VALUES ('draft', 'lost')"
        )
    assert memory.recall_workflow("draft") is None
    assert memory.recall_workflow("committed") == "kept"


def test_failed_atomic_write_preserves_previous_snapshot(protected, monkeypatch):
    path, protection = protected
    memory = OrganizationalMemory(path, protection=protection)
    memory.remember_workflow("saved", "original")
    original = path.read_bytes()
    monkeypatch.setattr(
        "app.protected_memory.os.replace", Mock(side_effect=OSError("disk failure"))
    )
    with pytest.raises(OSError):
        memory.remember_workflow("saved", "replacement")
    assert path.read_bytes() == original
    assert memory.recall_workflow("saved") == "original"
    assert not list(path.parent.glob(".memory-*"))


def test_memory_requires_a_key_and_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("ORGANIZATIONAL_MEMORY_ENABLED")
    monkeypatch.delenv("ORGANIZATIONAL_MEMORY_ENCRYPTION_KEY")
    assert not Settings(_env_file=None).organizational_memory_enabled
    with pytest.raises(ValidationError, match="requires ORGANIZATIONAL_MEMORY_ENCRYPTION_KEY"):
        Settings(_env_file=None, organizational_memory_enabled=True)


@pytest.mark.parametrize("days", [0, -1, 366])
def test_unbounded_retention_is_rejected(days):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, organizational_memory_retention_days=days)


def test_startup_retention_purges_without_user_requests(protected, monkeypatch):
    from app.memory_lifecycle import purge_memory

    path, protection = protected
    now = [1800000000.0]
    monkeypatch.setattr("app.protected_memory.time.time", lambda: now[0])
    memory, _, _ = populate(path, protection)
    settings = Settings(
        _env_file=None,
        organizational_memory_path=path,
        organizational_memory_encryption_key=protection.key,
        organizational_memory_retention_days=1,
    )
    now[0] += 86401
    purge_memory(settings)
    # Inspect persisted bytes directly; no further retention invocation is needed.
    with closing(sqlite3.connect(":memory:")) as db:
        db.deserialize(protection.read(path))
        assert db.execute("SELECT count(*) FROM test_suite_memory").fetchone()[0] == 0
    assert memory.count() == 0


def test_maintenance_cli_requires_confirmation_and_preserves_content(protected):
    import os
    import subprocess
    import sys

    path, protection = protected
    memory, _, _ = populate(path, protection)
    environment = dict(os.environ, ORGANIZATIONAL_MEMORY_ENCRYPTION_KEY=protection.key)
    command = [sys.executable, "-m", "app.memory_admin", "erase", str(path)]
    denied = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert denied.returncode != 0
    assert memory.count() == 1
    erased = subprocess.run(
        command + ["--confirm"], env=environment, capture_output=True, text=True
    )
    assert erased.returncode == 0
    assert memory.count() == 0
    assert protection.key not in denied.stderr + erased.stdout + erased.stderr


def test_disabled_memory_does_not_touch_legacy_data(tmp_path, monkeypatch):
    from app.memory_lifecycle import purge_memory

    path = tmp_path / "legacy.db"
    path.write_bytes(b"legacy data must remain untouched")
    original = path.read_bytes()
    settings = Settings(
        _env_file=None,
        organizational_memory_enabled=False,
        organizational_memory_path=path,
        organizational_memory_encryption_key="",
    )
    purge_memory(settings)
    memory = OrganizationalMemory(path, enabled=False, protection=settings.memory_protection)
    assert memory.count() == 0
    assert path.read_bytes() == original
