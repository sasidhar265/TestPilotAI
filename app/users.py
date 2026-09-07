"""Persistent accounts created and managed by administrators."""

import hashlib
import hmac
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from typing import Any

from app.config import Settings


@contextmanager
def database(settings: Settings) -> Iterator[sqlite3.Connection]:
    path = settings.user_database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.row_factory = sqlite3.Row
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY COLLATE NOCASE,
            display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
            enabled INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
            first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT ''
        )""")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        if "first_name" not in columns:
            connection.execute("BEGIN IMMEDIATE")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        if "first_name" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN first_name TEXT NOT NULL DEFAULT ''")
            connection.execute("ALTER TABLE users ADD COLUMN last_name TEXT NOT NULL DEFAULT ''")
            for row in connection.execute("SELECT username, display_name FROM users").fetchall():
                first, _, last = row["display_name"].partition(" ")
                connection.execute(
                    "UPDATE users SET first_name = ?, last_name = ? WHERE username = ?",
                    (first, last, row["username"]),
                )
        yield connection


def get_user(settings: Settings, username: str) -> dict[str, Any] | None:
    if username.casefold() == settings.app_username.casefold():
        return {
            "username": settings.app_username,
            "display_name": settings.app_display_name or settings.app_username,
            "role": "admin",
            "enabled": True,
            "version": 0,
            "managed": False,
        }
    with database(settings) as connection:
        row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) | {"managed": True} if row else None


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"{salt}:{digest.hex()}"


def authenticate(settings: Settings, username: str, password: str) -> dict[str, Any] | None:
    user = get_user(settings, username)
    if user and not user["managed"]:
        valid = hmac.compare_digest(password.encode(), settings.app_password_value.encode())
    else:
        # Perform a password derivation even for unknown accounts.
        stored = user["password_hash"] if user else "00" * 16 + ":" + "00" * 64
        valid = hmac.compare_digest(password_hash(password, stored.split(":")[0]), stored)
    return user if user and user["enabled"] and valid else None


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    result = {key: user[key] for key in ("username", "display_name", "role", "enabled", "managed")}
    first, _, last = user["display_name"].partition(" ")
    result.update(first_name=user.get("first_name", first), last_name=user.get("last_name", last))
    return result
