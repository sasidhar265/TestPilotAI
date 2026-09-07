import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.auth import SESSION_COOKIE, issue_browser_session, valid_session
from app.config import Settings, get_settings
from app.user_routes import router
from app.users import authenticate, database, get_user


@pytest.fixture
def account_app(tmp_path):
    settings = Settings(
        _env_file=None,
        app_username="owner",
        app_password=SecretStr("initial-admin-password"),
        session_secret=SecretStr("s" * 32),
        user_database_path=tmp_path / "users.db",
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, issue_browser_session("owner", settings))
    return client, settings


def create(client, **overrides):
    return client.post(
        "/api/admin/users",
        json={
            "username": "jane",
            "first_name": "Jane",
            "last_name": "Doe",
            "password": "a-long-test-password",
            **overrides,
        },
    )


def test_admin_creates_hashed_account_with_real_identity(account_app):
    client, settings = account_app
    response = create(client)
    assert response.status_code == 201
    assert "password" not in response.text
    assert response.json()["role"] == "user"
    assert authenticate(settings, "jane", "wrong-password") is None
    assert authenticate(settings, "JANE", "a-long-test-password") is not None
    with database(settings) as connection:
        stored = connection.execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored != "a-long-test-password"
    client.cookies.set(SESSION_COOKIE, issue_browser_session("jane", settings))
    profile = client.get("/api/auth/profile").json()
    assert profile["initials"] == "JD"
    assert not profile["is_admin"]
    assert client.get("/api/admin/users").status_code == 403
    assert client.get("/admin/users").status_code == 403
    assert create(client, username="intruder", role="admin").status_code == 403
    assert client.patch("/api/admin/users/owner/access", json={"enabled": False}).status_code == 403


def test_disabled_sessions_stay_revoked_after_reenable(account_app):
    client, settings = account_app
    assert create(client).status_code == 201
    session = issue_browser_session("jane", settings)
    assert valid_session(session, settings)
    assert client.patch("/api/admin/users/jane/access", json={"enabled": False}).status_code == 200
    assert not valid_session(session, settings)
    assert authenticate(settings, "jane", "a-long-test-password") is None
    assert client.patch("/api/admin/users/jane/access", json={"enabled": True}).status_code == 200
    assert not valid_session(session, settings)
    assert valid_session(issue_browser_session("jane", settings), settings)


def test_admin_boundaries_and_validation(account_app):
    client, settings = account_app
    assert create(client, username="OWNER").status_code == 409
    assert create(client, password="short").status_code == 422
    assert create(client, first_name=" ").status_code == 422
    assert create(client, role="superuser").status_code == 422
    assert create(client, enabled=False).status_code == 201
    assert create(client, username="JANE").status_code == 409
    assert not valid_session(issue_browser_session("jane", settings), settings)
    assert client.patch("/api/admin/users/owner/access", json={"enabled": False}).status_code == 409
    client.cookies.clear()
    assert client.get("/api/admin/users").status_code == 401
    assert create(client, username="outsider").status_code == 401
    assert (
        client.get("/api/admin/users", headers={"Authorization": "Bearer arbitrary"}).status_code
        == 401
    )


def test_created_admin_has_admin_access_but_cannot_disable_self(account_app):
    client, settings = account_app
    assert create(client, role="admin").status_code == 201
    client.cookies.set(SESSION_COOKIE, issue_browser_session("jane", settings))
    assert client.get("/api/auth/profile").json()["is_admin"]
    assert client.get("/api/admin/users").status_code == 200
    assert client.patch("/api/admin/users/jane/access", json={"enabled": False}).status_code == 409
    assert get_user(settings, "jane")["role"] == "admin"


def test_tampered_session_rejected(account_app):
    _, settings = account_app
    session = issue_browser_session("owner", settings)
    assert valid_session(session, settings)
    assert not valid_session(session + "x", settings)
    assert not valid_session("malformed", settings)


def test_new_user_login_and_revocation_through_middleware(account_app, monkeypatch):
    admin_client, settings = account_app
    assert create(admin_client).status_code == 201
    import app.main as main
    from app.observability import OrganizationHttpMiddleware

    monkeypatch.setattr(main, "settings_at_startup", settings)
    app = FastAPI()
    app.include_router(router)
    app.add_api_route("/api/auth/login", main.login, methods=["POST"])
    app.dependency_overrides[get_settings] = lambda: settings
    app.add_middleware(OrganizationHttpMiddleware, settings=settings)
    client = TestClient(app)
    assert client.get("/api/auth/profile").status_code == 401
    response = client.post(
        "/api/auth/login",
        json={
            "username": "jane",
            "password": "a-long-test-password",
        },
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert client.get("/api/auth/profile").json()["initials"] == "JD"
    assert client.get("/api/admin/users").status_code == 403
    admin_client.patch("/api/admin/users/jane/access", json={"enabled": False})
    assert client.get("/api/auth/profile").status_code == 401
    assert (
        client.post(
            "/api/auth/login",
            json={
                "username": "jane",
                "password": "a-long-test-password",
            },
        ).status_code
        == 401
    )


def test_admin_can_amend_role_and_access_together(account_app):
    client, settings = account_app
    assert create(client).status_code == 201
    session = issue_browser_session("jane", settings)
    response = client.patch("/api/admin/users/jane/access", json={"role": "admin", "enabled": True})
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert not valid_session(session, settings)
    promoted_session = issue_browser_session("jane", settings)
    client.cookies.set(SESSION_COOKIE, promoted_session)
    assert client.get("/api/admin/users").status_code == 200
    client.cookies.set(SESSION_COOKIE, issue_browser_session("owner", settings))
    response = client.patch("/api/admin/users/jane/access", json={"role": "user", "enabled": False})
    assert response.json()["role"] == "user"
    assert not response.json()["enabled"]
    assert not valid_session(promoted_session, settings)
    assert (
        client.patch(
            "/api/admin/users/jane/access", json={"role": "root", "enabled": True}
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/admin/users/owner/access", json={"role": "user", "enabled": True}
        ).status_code
        == 409
    )


def test_unchanged_access_preserves_session(account_app):
    client, settings = account_app
    assert create(client).status_code == 201
    session = issue_browser_session("jane", settings)
    assert (
        client.patch(
            "/api/admin/users/jane/access", json={"role": "user", "enabled": True}
        ).status_code
        == 200
    )
    assert valid_session(session, settings)


def test_edit_user_details_and_optional_password(account_app):
    client, settings = account_app
    assert create(client, first_name="Mary Jane", last_name="Van Doe").status_code == 201
    original = client.get("/api/admin/users").json()[1]
    assert original["first_name"] == "Mary Jane"
    assert original["last_name"] == "Van Doe"
    payload = dict(first_name="Jane Marie", last_name="Smith Jones", role="admin", enabled=True)
    session = issue_browser_session("jane", settings)
    result = client.patch("/api/admin/users/jane", json=payload)
    assert result.status_code == 200
    assert result.json()["first_name"] == "Jane Marie"
    assert result.json()["last_name"] == "Smith Jones"
    assert authenticate(settings, "jane", "a-long-test-password")
    assert not valid_session(session, settings)
    payload["password"] = "a-new-long-password"
    assert client.patch("/api/admin/users/jane", json=payload).status_code == 200
    assert authenticate(settings, "jane", "a-long-test-password") is None
    assert authenticate(settings, "jane", "a-new-long-password")
    assert client.patch("/api/admin/users/owner", json=payload).status_code == 409
    payload["password"] = "short"
    assert client.patch("/api/admin/users/jane", json=payload).status_code == 422
    assert create(client, username="ordinary").status_code == 201
    client.cookies.set(SESSION_COOKIE, issue_browser_session("ordinary", settings))
    payload.pop("password")
    assert client.patch("/api/admin/users/jane", json=payload).status_code == 403


def test_delete_account_revokes_access_even_after_username_reuse(account_app):
    client, settings = account_app
    assert create(client).status_code == 201
    session = issue_browser_session("jane", settings)
    assert client.delete("/api/admin/users/owner").status_code == 409
    assert client.delete("/api/admin/users/jane").status_code == 200
    assert not valid_session(session, settings)
    assert authenticate(settings, "jane", "a-long-test-password") is None
    assert client.delete("/api/admin/users/jane").status_code == 404
    assert create(client).status_code == 201
    assert not valid_session(session, settings)
    client.cookies.set(SESSION_COOKIE, issue_browser_session("jane", settings))
    assert client.delete("/api/admin/users/owner").status_code == 403
    client.cookies.clear()
    assert client.delete("/api/admin/users/jane").status_code == 401
