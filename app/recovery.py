"""Consistent, verified SQLite snapshots and restore drills into new directories only."""

import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.audit_integrity import verify_audit


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_private_json(path: Path, data: dict[str, Any]) -> None:
    """Do not replace existing evidence or follow a destination symlink."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def check_database(db: sqlite3.Connection) -> dict[str, Any] | None:
    if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("SQLite integrity check failed")
    if db.execute("PRAGMA foreign_key_check").fetchone():
        raise ValueError("SQLite foreign-key check failed")
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "audit" in tables:
        return verify_audit(db)
    return None


def snapshot_database(source: Path, destination: Path) -> dict[str, Any] | None:
    if not source.is_file():
        raise ValueError("Source database must exist")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    started = time.monotonic()

    def progress(status: int, remaining: int, total: int) -> None:
        if time.monotonic() - started > 60:
            raise TimeoutError("Database snapshot exceeded 60 seconds")

    with (
        closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as origin,
        closing(sqlite3.connect(destination)) as target,
    ):
        origin.backup(target, pages=256, progress=progress)
        return check_database(target)


def backup_database(source: Path, destination: Path) -> dict[str, Any]:
    """Create a new restricted bundle; a failed bundle has no completion manifest."""
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    snapshot = destination / "database.sqlite3"
    audit = snapshot_database(source, snapshot)
    manifest = {
        "format": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "sha256": file_digest(snapshot),
        "bytes": snapshot.stat().st_size,
        "audit_checkpoint": audit,
    }
    write_private_json(destination / "manifest.json", manifest)
    return manifest


def restore_database(bundle: Path, destination: Path) -> dict[str, Any]:
    """Validate a bundle and restore to a fresh directory, never over a live database."""
    manifest = json.loads((bundle / "manifest.json").read_text())
    snapshot = bundle / "database.sqlite3"
    if not isinstance(manifest, dict) or manifest.get("format") != 1:
        raise ValueError("Unsupported backup format")
    if file_digest(snapshot) != manifest.get("sha256"):
        raise ValueError("Backup checksum mismatch")
    if snapshot.stat().st_size != manifest.get("bytes"):
        raise ValueError("Backup size mismatch")
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    started = time.monotonic()
    audit = snapshot_database(snapshot, destination / "database.sqlite3")
    if audit != manifest.get("audit_checkpoint"):
        raise ValueError("Restored audit checkpoint mismatch")
    report = {
        "status": "restore-verified",
        "verified_at": datetime.now(UTC).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "source_sha256": manifest["sha256"],
        "audit_checkpoint": audit,
        "scope": "One SQLite database; application recovery and RTO/RPO are not verified.",
    }
    write_private_json(destination / "restore-report.json", report)
    return report
