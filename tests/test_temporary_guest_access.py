"""Unit checks for the temporary access deadline and authorization policy."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.auth import GUEST_COOKIE, issue_guest_session, valid_guest_session
from app.config import Settings
from app.observability import OrganizationHttpMiddleware


def configured(**overrides):
    return Settings(
        _env_file=None,
        environment="production",
        api_auth_token="a" * 32,
        app_password="password-for-testing",
        session_secret="s" * 32,
        allowed_hosts="testserver",
        **overrides,
    )


@pytest.mark.parametrize("deadline", [None, "", "2020-01-01T00:00:00Z"])
def test_guest_access_is_disabled_without_a_future_deadline(deadline):
    assert not configured(temporary_guest_access_until=deadline).temporary_guest_access_active


@pytest.mark.parametrize("deadline", ["not-a-date", "2026-09-25T23:59:00"])
def test_deadline_requires_a_valid_timezone(deadline):
    with pytest.raises(ValidationError):
        configured(temporary_guest_access_until=deadline)


def test_expiry_is_checked_without_reloading_settings(monkeypatch):
    deadline = datetime(2026, 9, 25, tzinfo=UTC)
    settings = configured(temporary_guest_access_until=deadline)
    clock = Mock()
    monkeypatch.setattr("app.config.datetime", clock)
    clock.now.return_value = deadline - timedelta(seconds=1)
    assert settings.temporary_guest_access_active
    clock.now.return_value = deadline
    assert not settings.temporary_guest_access_active
    assert settings.browser_login_enabled


@pytest.mark.parametrize(
    "path", ["/", "/progress", "/api/dashboard", "/api/automation/history", "/api/auth/profile"]
)
def test_guest_policy_expires_for_workspace_paths(path, monkeypatch):
    deadline = datetime(2026, 9, 25, tzinfo=UTC)
    settings = configured(temporary_guest_access_until=deadline)
    middleware = OrganizationHttpMiddleware(Mock(), settings)
    clock = Mock()
    monkeypatch.setattr("app.config.datetime", clock)
    clock.now.return_value = deadline - timedelta(seconds=1)
    monkeypatch.setattr("app.auth.time.time", lambda: clock.now.return_value.timestamp())
    guest = issue_guest_session(settings)
    headers = {b"cookie": f"{GUEST_COOKIE}={guest}".encode()}
    assert not middleware._authorized({"path": path}, {})
    assert middleware._authorized({"path": path}, headers)
    clock.now.return_value = deadline
    assert not middleware._authorized({"path": path}, headers)
    assert middleware._authorized(
        {"path": "/api/generate"}, {b"authorization": b"Bearer " + b"a" * 32}
    )


@pytest.mark.parametrize("path", ["/admin/users", "/api/admin/users", "/api/admin/users/example"])
def test_guest_policy_does_not_allow_account_administration(path):
    settings = configured(temporary_guest_access_until=datetime.now(UTC) + timedelta(days=2))
    middleware = OrganizationHttpMiddleware(Mock(), settings)
    assert not middleware._authorized({"path": path}, {})


@pytest.mark.parametrize(
    "path,method",
    [
        ("/project-dashboard", "GET"),
        ("/quality-lifecycle", "GET"),
        ("/knowledge", "GET"),
        ("/logs", "GET"),
        ("/docs", "GET"),
        ("/openapi.json", "GET"),
        ("/static/index.html", "GET"),
        ("/static/user-guide.html", "GET"),
        ("/api/admin/users", "GET"),
        ("/api/workspace/knowledge", "GET"),
        ("/api/logs", "GET"),
        ("/api/generate", "POST"),
        ("/api/automation/run", "POST"),
        ("/api/workspace/rules", "PUT"),
        ("/api/dashboard", "POST"),
    ],
)
def test_signed_guest_cannot_escape_view_only_scope(path, method):
    settings = configured(temporary_guest_access_until=datetime.now(UTC) + timedelta(days=14))
    middleware = OrganizationHttpMiddleware(Mock(), settings)
    headers = {b"cookie": f"{GUEST_COOKIE}={issue_guest_session(settings)}".encode()}
    scope = {"path": path, "method": method}
    assert not middleware._authorized(scope, headers)
    assert scope["guest_access_denied"]


def test_guest_signature_and_revocation():
    settings = configured(temporary_guest_access_until=datetime.now(UTC) + timedelta(days=14))
    token = issue_guest_session(settings)
    assert valid_guest_session(token, settings)
    assert not valid_guest_session(token + "x", settings)
    assert not valid_guest_session("guest.invalid.signature", settings)
    settings.temporary_guest_access_until = None
    assert not valid_guest_session(token, settings)


def test_guest_cookie_does_not_replace_account_or_bearer_authorization(tmp_path):
    from app.auth import SESSION_COOKIE, issue_browser_session

    settings = configured(
        temporary_guest_access_until=datetime.now(UTC) + timedelta(days=14),
        user_database_path=tmp_path / "users.db",
    )
    middleware = OrganizationHttpMiddleware(Mock(), settings)
    guest = f"{GUEST_COOKIE}={issue_guest_session(settings)}"
    session = issue_browser_session(settings.app_username, settings)
    assert middleware._authorized(
        {"path": "/admin/users"},
        {
            b"cookie": f"{guest}; {SESSION_COOKIE}={session}".encode(),
        },
    )
    assert middleware._authorized(
        {"path": "/api/generate", "method": "POST"},
        {
            b"cookie": guest.encode(),
            b"authorization": b"Bearer " + b"a" * 32,
        },
    )


def test_guest_entry_requires_a_signing_secret():
    settings = Settings(
        _env_file=None,
        session_secret="",
        temporary_guest_access_until=datetime.now(UTC) + timedelta(days=14),
    )
    assert not settings.temporary_guest_access_active
    with pytest.raises(ValueError, match="unavailable"):
        issue_guest_session(settings)
