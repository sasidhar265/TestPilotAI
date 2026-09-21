import json
import sqlite3
import subprocess
import sys

import pytest

from app.audit_integrity import append_event, initialize_audit, verify_audit
from app.recovery import backup_database, restore_database
from app.resilience import readiness_report
from app.services.stlc import LifecycleStore


@pytest.fixture
def database(tmp_path):
    store = LifecycleStore(tmp_path / "memory.db")
    with store.transaction() as db:
        append_event(db, ("record", "created", "author", "", "2026-09-21"))
    return store.path


def test_legacy_migration_preserves_events_and_is_repeatable(tmp_path):
    path = tmp_path / "stlc.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE audit(sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
            "record_id TEXT, action TEXT, actor TEXT, comment TEXT, created_at TEXT)"
        )
        db.execute("INSERT INTO audit VALUES(1,'r','created','author','original','date')")
        initialize_audit(db)
        initialize_audit(db)
        assert verify_audit(db)["legacy_events"] == 1
        assert db.execute("SELECT comment FROM audit").fetchone()[0] == "original"
        append_event(db, ("r", "approved", "reviewer", "reviewed", "date"))
        assert verify_audit(db)["events"] == 2


@pytest.mark.parametrize("statement", ["UPDATE audit SET actor='other'", "DELETE FROM audit"])
def test_normal_audit_mutation_is_blocked(database, statement):
    with sqlite3.connect(database) as db:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            db.execute(statement)


def test_tampering_is_detected_and_store_fails_closed(database):
    with sqlite3.connect(database) as db:
        db.execute("DROP TRIGGER audit_no_update")
        db.execute("UPDATE audit SET actor='other'")
    with pytest.raises(ValueError, match="integrity failure"):
        LifecycleStore(database)


def test_replace_cannot_overwrite_audit_event(database):
    with sqlite3.connect(database) as db:
        with pytest.raises(sqlite3.IntegrityError, match="append in sequence"):
            db.execute("INSERT OR REPLACE INTO audit SELECT * FROM audit WHERE sequence=1")


@pytest.mark.parametrize("checkpoint", [{}, [], {"events": -1, "head": "0" * 64}])
def test_invalid_checkpoint_is_rejected(database, checkpoint):
    with sqlite3.connect(database) as db:
        with pytest.raises(ValueError, match="Invalid audit checkpoint"):
            verify_audit(db, checkpoint)


def test_checkpoint_detects_truncation_and_allows_new_events(database):
    with sqlite3.connect(database) as db:
        checkpoint = verify_audit(db)
        append_event(db, ("r", "approved", "reviewer", "", "date"))
        assert verify_audit(db, checkpoint)["events"] == 2
        checkpoint = verify_audit(db)
        db.execute("DROP TRIGGER audit_no_delete")
        db.execute("DELETE FROM audit WHERE sequence=2")
        with pytest.raises(ValueError, match="checkpoint missing"):
            verify_audit(db, checkpoint)


def test_backup_restore_preserves_committed_wal_data(database, tmp_path):
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA journal_mode=WAL")
        append_event(db, ("r", "approved", "reviewer", "", "date"))
        db.commit()
        bundle = tmp_path / "backup"
        manifest = backup_database(database, bundle)
        assert manifest["audit_checkpoint"]["events"] == 2
        restored = tmp_path / "restored"
        report = restore_database(bundle, restored)
        assert report["status"] == "restore-verified"
        assert readiness_report(restored / "database.sqlite3")["audit"]["events"] == 2
        assert (bundle.stat().st_mode & 0o777) == 0o700
        assert ((bundle / "database.sqlite3").stat().st_mode & 0o777) == 0o600
        with pytest.raises(FileExistsError):
            restore_database(bundle, restored)
        with pytest.raises(FileExistsError):
            backup_database(database, bundle)


def test_damaged_backup_is_rejected_before_restore(database, tmp_path):
    bundle = tmp_path / "backup"
    backup_database(database, bundle)
    with (bundle / "database.sqlite3").open("ab") as stream:
        stream.write(b"tampering")
    with pytest.raises(ValueError, match="checksum mismatch"):
        restore_database(bundle, tmp_path / "restore")
    assert not (tmp_path / "restore").exists()


def test_failed_backup_has_no_completion_manifest(tmp_path):
    with pytest.raises(ValueError, match="must exist"):
        backup_database(tmp_path / "missing.db", tmp_path / "backup")
    assert not (tmp_path / "backup" / "manifest.json").exists()


def test_operator_commands_and_checkpoint(database, tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.resilience",
            "audit",
            str(database),
            "--export-checkpoint",
            str(checkpoint),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["events"] == 1
    report = readiness_report(database, checkpoint)
    assert report["compliance_status"] == "not-established"
    assert report["independent_checkpoint_supplied"] is True
    assert len(report["open_requirements"]) == 8
    failed = subprocess.run(
        [sys.executable, "-m", "app.resilience", "audit", str(tmp_path / "missing.db")],
        capture_output=True,
        text=True,
    )
    assert failed.returncode == 1
    assert not (tmp_path / "missing.db").exists()


def test_null_checkpoint_file_cannot_bypass_verification(database, tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text("null")
    with pytest.raises(ValueError, match="Invalid audit checkpoint"):
        readiness_report(database, checkpoint)
