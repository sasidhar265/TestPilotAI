"""Offline organisational-memory maintenance; never outputs stored content or keys."""

import argparse
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from filelock import FileLock

from app.protected_memory import TABLES, MemoryProtection, MemoryProtectionError


def migrate(source: Path, destination: Path, protection: MemoryProtection) -> None:
    """Copy a quiesced legacy SQLite database into a new encrypted snapshot."""
    protection.cipher()
    if not source.is_file() or source.resolve() == destination.resolve():
        raise MemoryProtectionError(
            "Migration requires an existing source and a different destination."
        )
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with FileLock(str(destination) + ".lock", timeout=5, mode=0o600):
        if destination.exists():
            raise MemoryProtectionError(
                "Migration destination already exists; refusing to replace it."
            )
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as legacy:
            with closing(sqlite3.connect(":memory:")) as memory:
                legacy.backup(memory)
                if memory.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise MemoryProtectionError("Legacy memory integrity check failed.")
                # Older memory writers used WAL. A serialized in-memory image must use DELETE.
                memory.execute("PRAGMA journal_mode=DELETE")
                memory.create_function("memory_now", 0, time.time)
                protection.prepare(memory)
                snapshot = bytearray(memory.serialize())
                # SQLite documents rollback-format headers for deserializing a WAL snapshot.
                # https://www.sqlite.org/c3ref/deserialize.html
                snapshot[18:20] = b"\x01\x01"
                protection.write(destination, bytes(snapshot))


def erase(path: Path, protection: MemoryProtection) -> None:
    with closing(protection.connect(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table in ["output_scenarios", *TABLES]:
            if table in tables:
                connection.execute(f"DELETE FROM {table}")
        connection.commit()
        connection.execute("VACUUM")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["migrate", "purge-expired", "erase"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--confirm", action="store_true", help="Confirm erasing all memory content")
    args = parser.parse_args()
    protection = MemoryProtection.from_environment()
    try:
        if args.command == "migrate":
            if args.destination is None:
                parser.error("migrate requires --destination")
            migrate(args.path, args.destination, protection)
        elif args.command == "erase":
            if not args.confirm:
                parser.error("erase requires --confirm")
            if not args.path.is_file():
                parser.error("memory store does not exist")
            erase(args.path, protection)
        else:
            if not args.path.is_file():
                parser.error("memory store does not exist")
            with closing(protection.connect(args.path)):
                pass
    except (MemoryProtectionError, sqlite3.Error, OSError) as error:
        # Avoid exception text from file/SQLite operations leaking paths or payload values.
        parser.exit(
            1, f"Memory maintenance failed ({type(error).__name__}). No content exported.\n"
        )
    print(
        "Memory maintenance completed. Backups and legacy source copies require separate handling."
    )


if __name__ == "__main__":
    main()
