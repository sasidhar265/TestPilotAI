"""Append-only lifecycle audit chain; export checkpoints to independently protected storage."""

import hashlib
import json
import sqlite3
from typing import Any

GENESIS = "0" * 64


def digest_event(previous: str, values: tuple[Any, ...]) -> str:
    data = json.dumps([previous, *values], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def initialize_audit(db: sqlite3.Connection) -> None:
    """Migrate existing events transactionally without claiming historical authenticity."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(audit)")}
    if "event_hash" not in columns:
        db.execute("ALTER TABLE audit ADD COLUMN previous_hash TEXT NOT NULL DEFAULT ''")
        db.execute("ALTER TABLE audit ADD COLUMN event_hash TEXT NOT NULL DEFAULT ''")
        db.execute(
            "CREATE TABLE audit_chain_metadata "
            "(id INTEGER PRIMARY KEY CHECK(id=1), legacy_events INTEGER NOT NULL)"
        )
        rows = db.execute(
            "SELECT sequence,record_id,action,actor,comment,created_at FROM audit ORDER BY sequence"
        ).fetchall()
        previous = GENESIS
        for row in rows:
            digest = digest_event(previous, tuple(row))
            db.execute(
                "UPDATE audit SET previous_hash=?,event_hash=? WHERE sequence=?",
                (previous, digest, row[0]),
            )
            previous = digest
        db.execute("INSERT INTO audit_chain_metadata VALUES(1,?)", (len(rows),))
    for operation in ("UPDATE", "DELETE"):
        db.execute(
            f"CREATE TRIGGER IF NOT EXISTS audit_no_{operation.lower()} "
            f"BEFORE {operation} ON audit BEGIN "
            "SELECT RAISE(ABORT, 'Audit events are append-only'); END"
        )
    db.execute(
        "CREATE TRIGGER IF NOT EXISTS audit_sequential_insert BEFORE INSERT ON audit "
        "WHEN NEW.sequence != COALESCE((SELECT MAX(sequence) FROM audit),0)+1 "
        "BEGIN SELECT RAISE(ABORT, 'Audit events must append in sequence'); END"
    )


def append_event(db: sqlite3.Connection, values: tuple[str, str, str, str, str]) -> None:
    last = db.execute(
        "SELECT sequence,event_hash FROM audit ORDER BY sequence DESC LIMIT 1"
    ).fetchone()
    sequence, previous = (last[0] + 1, last[1]) if last else (1, GENESIS)
    db.execute(
        "INSERT INTO audit(sequence,record_id,action,actor,comment,created_at,"
        "previous_hash,event_hash) VALUES(?,?,?,?,?,?,?,?)",
        (sequence, *values, previous, digest_event(previous, (sequence, *values))),
    )


def verify_audit(
    db: sqlite3.Connection, checkpoint: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Verify the full chain and, optionally, a previously trusted prefix checkpoint."""
    if checkpoint is not None and (
        not isinstance(checkpoint, dict)
        or type(checkpoint.get("events")) is not int
        or checkpoint["events"] < 0
        or not isinstance(checkpoint.get("head"), str)
        or len(checkpoint["head"]) != 64
    ):
        raise ValueError("Invalid audit checkpoint")
    previous = GENESIS
    count = 0
    anchored = checkpoint is None
    for row in db.execute(
        "SELECT sequence,record_id,action,actor,comment,created_at,previous_hash,event_hash "
        "FROM audit ORDER BY sequence"
    ):
        count += 1
        if (
            row[0] != count
            or row[6] != previous
            or row[7] != digest_event(previous, tuple(row[:6]))
        ):
            raise ValueError(f"Audit integrity failure at event {count}")
        previous = row[7]
        if checkpoint and count == checkpoint.get("events"):
            if previous != checkpoint.get("head"):
                raise ValueError("Audit checkpoint mismatch")
            anchored = True
    if checkpoint and checkpoint.get("events") == 0 and checkpoint.get("head") == GENESIS:
        anchored = True
    if not anchored:
        raise ValueError("Audit checkpoint missing: possible truncation or wrong database")
    metadata = db.execute("SELECT legacy_events FROM audit_chain_metadata WHERE id=1").fetchone()
    if metadata is None:
        raise ValueError("Audit migration metadata is missing")
    return {"events": count, "head": previous, "legacy_events": metadata[0]}
