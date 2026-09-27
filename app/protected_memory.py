"""Encrypted SQLite snapshots: plaintext exists only in process memory.

The whole small, single-node knowledge store is authenticated and encrypted. An
inter-process lock serializes transactions; atomic replacement preserves the last
committed snapshot. This is not the application's lifecycle/evidence database.
"""

import os
import sqlite3
import tempfile
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from filelock import FileLock

MAGIC = b"AFQ-MEMORY-1\n"
TABLES = {
    "test_suite_memory": "suite_json",
    "review_feedback": "comments, suite_json",
    "workflow_memory": "artifact_json",
    "reqnroll_memory": "artifact_json",
    "converted_outputs": "content, suite_json",
}


class MemoryProtectionError(RuntimeError):
    """A safe, payload-free error suitable for operator diagnostics."""


def validate_key(key: str) -> None:
    try:
        Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError) as error:
        raise MemoryProtectionError(
            "ORGANIZATIONAL_MEMORY_ENCRYPTION_KEY must be a valid Fernet key."
        ) from error


class ProtectedConnection(sqlite3.Connection):
    protection: "MemoryProtection"
    destination: Path
    file_lock: FileLock
    original: bytes
    closed: bool = False

    def abort(self) -> None:
        """Release resources without replacing the last valid encrypted snapshot."""
        if not self.closed:
            self.closed = True
            super().close()
            self.file_lock.release()

    def close(self) -> None:
        if self.closed:
            return
        try:
            # Match sqlite3: closing must not commit a caller's unfinished transaction.
            self.rollback()
            snapshot = self.serialize()
            if snapshot != self.original:
                self.protection.write(self.destination, snapshot)
        finally:
            self.closed = True
            super().close()
            self.file_lock.release()


class MemoryProtection:
    def __init__(self, key: str, retention_days: int = 30) -> None:
        if not 1 <= retention_days <= 365:
            raise ValueError("Memory retention must be between 1 and 365 days.")
        self.key = key
        self.retention_days = retention_days

    @classmethod
    def from_environment(cls) -> "MemoryProtection":
        return cls(
            os.environ.get("ORGANIZATIONAL_MEMORY_ENCRYPTION_KEY", ""),
            int(os.environ.get("ORGANIZATIONAL_MEMORY_RETENTION_DAYS", "30")),
        )

    def cipher(self) -> Fernet:
        validate_key(self.key)
        return Fernet(self.key.encode("ascii"))

    def read(self, path: Path) -> bytes:
        value = path.read_bytes()
        if not value.startswith(MAGIC):
            raise MemoryProtectionError(
                "Plaintext or unsupported memory store refused. Stop the application and use "
                "python -m app.memory_admin migrate with a new destination."
            )
        try:
            return self.cipher().decrypt(value[len(MAGIC) :])
        except InvalidToken as error:
            raise MemoryProtectionError(
                "Memory key mismatch or encrypted store corruption."
            ) from error

    def write(self, path: Path, snapshot: bytes) -> None:
        encrypted = MAGIC + self.cipher().encrypt(snapshot)
        descriptor, temporary = tempfile.mkstemp(prefix=".memory-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def connect(self, path: Path) -> ProtectedConnection:
        self.cipher()  # Fail before creating any file when the key is absent/invalid.
        path = path.absolute()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink():
            raise MemoryProtectionError("Memory store must not be a symbolic link.")
        path = path.resolve()
        lock = FileLock(str(path) + ".lock", timeout=5, mode=0o600)
        lock.acquire()
        connection = sqlite3.connect(":memory:", factory=ProtectedConnection)
        try:
            connection.protection = self
            connection.destination = path
            connection.file_lock = lock
            connection.create_function("memory_now", 0, time.time)
            if path.exists():
                connection.deserialize(self.read(path))
            # Ensure even a brand-new SQLite connection is serializable.
            connection.execute("CREATE TABLE IF NOT EXISTS memory_format (version INTEGER)")
            connection.commit()
            connection.original = connection.serialize()
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("PRAGMA temp_store=MEMORY")
            self.prepare(connection)
            return connection
        except BaseException:
            sqlite3.Connection.close(connection)
            lock.release()
            raise

    def prepare(self, connection: sqlite3.Connection) -> None:
        """Attach expiry to every cache, including converted output and C# knowledge."""
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table, content_columns in TABLES.items():
            if table not in tables:
                continue
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            if "retained_at" not in columns:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN retained_at REAL NOT NULL DEFAULT 0"
                )
                timestamp = "memory_now()"
                if "created_at" in columns:
                    timestamp = "COALESCE(CAST(strftime('%s', created_at) AS REAL), memory_now())"
                connection.execute(f"UPDATE {table} SET retained_at = {timestamp}")
            connection.execute(
                f"CREATE TRIGGER IF NOT EXISTS {table}_retention_insert AFTER INSERT ON {table} "
                f"BEGIN UPDATE {table} SET retained_at = memory_now() WHERE rowid = NEW.rowid; END"
            )
            connection.execute(
                f"CREATE TRIGGER IF NOT EXISTS {table}_retention_update "
                f"AFTER UPDATE OF {content_columns} ON {table} "
                f"BEGIN UPDATE {table} SET retained_at = memory_now() WHERE rowid = NEW.rowid; END"
            )
        cutoff = time.time() - self.retention_days * 86400
        if {"converted_outputs", "output_scenarios"} <= tables:
            connection.execute(
                "DELETE FROM output_scenarios WHERE artifact_id IN "
                "(SELECT artifact_id FROM converted_outputs WHERE retained_at <= ?)",
                (cutoff,),
            )
        for table in TABLES.keys() & tables:
            connection.execute(f"DELETE FROM {table} WHERE retained_at <= ?", (cutoff,))
        connection.commit()
