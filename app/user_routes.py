"""Administrator-only account management and current-user identity."""

import secrets
import sqlite3
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth import GUEST_COOKIE, SESSION_COOKIE, session_username, valid_guest_session
from app.config import Settings, get_settings
from app.users import database, get_user, password_hash, public_user

router = APIRouter()
Config = Annotated[Settings, Depends(get_settings)]


def current_user(request: Request, settings: Config) -> dict[str, Any]:
    username = session_username(request.cookies.get(SESSION_COOKIE, ""), settings)
    user = get_user(settings, username) if username else None
    if user is None and valid_guest_session(request.cookies.get(GUEST_COOKIE, ""), settings):
        return {
            "username": "temporary-guest",
            "display_name": "Guest",
            "role": "guest",
            "enabled": True,
            "managed": False,
        }
    if user is None:
        raise HTTPException(401, "Sign in to access your account")
    return user


def require_admin(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(403, "Only administrators can manage users")
    return user


Admin = Annotated[dict[str, Any], Depends(require_admin)]


class NewUser(BaseModel):
    username: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.@-]*$")
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "user"] = "user"
    enabled: bool = True


class UserAccess(BaseModel):
    enabled: bool
    role: Literal["admin", "user"] | None = None


@router.get("/api/auth/profile", include_in_schema=False)
def profile(
    user: Annotated[dict[str, Any], Depends(current_user)], settings: Config
) -> dict[str, Any]:
    parts = user["display_name"].split()
    initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "?"
    deadline = settings.temporary_guest_access_until
    return public_user(user) | {
        "initials": initials,
        "is_admin": user["role"] == "admin",
        "is_guest": user["role"] == "guest",
        "guest_access_until": deadline.isoformat()
        if deadline and user["role"] == "guest" and settings.temporary_guest_access_active
        else None,
    }


@router.get("/admin/users", include_in_schema=False)
def users_page(admin: Admin) -> FileResponse:
    return FileResponse(
        Path(__file__).parent / "static" / "users.html", headers={"Cache-Control": "no-store"}
    )


@router.get("/api/admin/users")
def list_users(settings: Config, admin: Admin) -> list[dict[str, Any]]:
    with database(settings) as connection:
        rows = connection.execute("SELECT * FROM users ORDER BY username").fetchall()
    bootstrap = get_user(settings, settings.app_username)
    assert bootstrap is not None
    return [public_user(bootstrap)] + [public_user(dict(row) | {"managed": True}) for row in rows]


@router.post("/api/admin/users", status_code=201)
def create_user(payload: NewUser, settings: Config, admin: Admin) -> dict[str, Any]:
    if not payload.first_name.strip() or not payload.last_name.strip():
        raise HTTPException(422, "First and last names cannot be blank")
    if get_user(settings, payload.username):
        raise HTTPException(409, "Username already exists")
    try:
        with database(settings) as connection:
            connection.execute(
                "INSERT INTO users (username, display_name, password_hash, role, enabled, "
                "first_name, last_name, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    payload.username,
                    f"{payload.first_name.strip()} {payload.last_name.strip()}",
                    password_hash(payload.password),
                    payload.role,
                    payload.enabled,
                    payload.first_name.strip(),
                    payload.last_name.strip(),
                    secrets.randbits(52) + 1,
                ),
            )
    except sqlite3.IntegrityError as error:
        raise HTTPException(409, "Username already exists") from error
    created = get_user(settings, payload.username)
    assert created is not None
    return public_user(created)


@router.patch("/api/admin/users/{username}/access")
def update_access(
    username: str, payload: UserAccess, settings: Config, admin: Admin
) -> dict[str, Any]:
    user = get_user(settings, username)
    if user is None:
        raise HTTPException(404, "User not found")
    if not user["managed"] or username.casefold() == admin["username"].casefold():
        raise HTTPException(409, "You cannot change your own access or the initial admin account")
    with database(settings) as connection:
        connection.execute(
            "UPDATE users SET enabled = ?, role = COALESCE(?, role), version = version + 1 "
            "WHERE username = ? AND (enabled != ? OR role != COALESCE(?, role))",
            (payload.enabled, payload.role, username, payload.enabled, payload.role),
        )
    updated = get_user(settings, username)
    assert updated is not None
    return public_user(updated)


class UserUpdate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: Literal["admin", "user"]
    enabled: bool
    password: str | None = Field(default=None, min_length=12, max_length=256)


@router.patch("/api/admin/users/{username}")
def update_user(
    username: str, payload: UserUpdate, settings: Config, admin: Admin
) -> dict[str, Any]:
    user = get_user(settings, username)
    if user is None:
        raise HTTPException(404, "User not found")
    if not user["managed"] or username.casefold() == admin["username"].casefold():
        raise HTTPException(409, "You cannot edit your own account or the initial admin account")
    first, last = payload.first_name.strip(), payload.last_name.strip()
    if not first or not last:
        raise HTTPException(422, "First and last names cannot be blank")
    hashed = password_hash(payload.password) if payload.password is not None else None
    with database(settings) as connection:
        connection.execute(
            "UPDATE users SET first_name = ?, last_name = ?, display_name = ?, "
            "role = ?, enabled = ?, password_hash = COALESCE(?, password_hash), "
            "version = version + 1 WHERE username = ?",
            (first, last, f"{first} {last}", payload.role, payload.enabled, hashed, username),
        )
    updated = get_user(settings, username)
    assert updated is not None
    return public_user(updated)


@router.delete("/api/admin/users/{username}")
def delete_user(username: str, settings: Config, admin: Admin) -> dict[str, bool]:
    user = get_user(settings, username)
    if user is None:
        raise HTTPException(404, "User not found")
    if not user["managed"] or username.casefold() == admin["username"].casefold():
        raise HTTPException(409, "You cannot delete your own account or the initial admin account")
    with database(settings) as connection:
        connection.execute("DELETE FROM users WHERE username = ?", (username,))
    return {"deleted": True}
