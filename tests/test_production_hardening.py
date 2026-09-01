import pytest
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.auth import SESSION_COOKIE, issue_browser_session
from app.config import Settings
from app.main import app
from app.observability import LifecycleEventRegistry, OrganizationHttpMiddleware


async def protected_endpoint(request) -> JSONResponse:
    return JSONResponse({"ok": True})


def hardened_client(settings: Settings) -> TestClient:
    application = Starlette(routes=[Route("/api/protected", protected_endpoint, methods=["POST"])])
    application.add_middleware(OrganizationHttpMiddleware, settings=settings)
    return TestClient(application)


def test_production_configuration_requires_strong_authentication_token() -> None:
    with pytest.raises(ValidationError, match="API_AUTH_TOKEN"):
        Settings(environment="production")


def test_production_configuration_rejects_wildcard_hosts() -> None:
    with pytest.raises(ValidationError, match="ALLOWED_HOSTS"):
        Settings(environment="production", api_auth_token="x" * 32, allowed_hosts="*")


def test_request_and_upload_limits_must_leave_multipart_overhead() -> None:
    with pytest.raises(ValidationError, match="MAX_UPLOAD_BYTES"):
        Settings(max_request_body_bytes=1024, max_upload_bytes=1024)


def test_coordinator_timeout_covers_both_specialists_and_revisions() -> None:
    with pytest.raises(ValidationError, match="COPILOT_COORDINATOR_TIMEOUT_SECONDS"):
        Settings(copilot_timeout_seconds=300, copilot_coordinator_timeout_seconds=1199)


def test_default_coordinator_timeout_covers_governed_generation_budget() -> None:
    settings = Settings(_env_file=None)

    assert settings.copilot_coordinator_timeout_seconds >= settings.copilot_timeout_seconds * 4


def test_completed_lifecycle_rejects_late_callback_events() -> None:
    events = LifecycleEventRegistry()
    events.publish("request-1", "QA Master", "coordinate", "running", "Started")
    events.complete("request-1")
    events.publish("request-1", "Late specialist", "generate", "success", "Too late")

    snapshot = events.read("request-1")

    assert snapshot["complete"] is True
    assert len(snapshot["events"]) == 1


def test_api_authentication_is_enforced_when_configured() -> None:
    settings = Settings(api_auth_token="a" * 32)
    client = hardened_client(settings)

    missing = client.post("/api/protected", json={"value": "safe"})
    invalid = client.post(
        "/api/protected",
        json={"value": "safe"},
        headers={"Authorization": "Bearer wrong"},
    )
    accepted = client.post(
        "/api/protected",
        json={"value": "safe"},
        headers={"Authorization": f"Bearer {settings.api_auth_token_value}"},
    )

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert invalid.status_code == 401
    assert accepted.status_code == 200


def test_browser_login_redirects_pages_and_authorizes_api_with_signed_cookie() -> None:
    settings = Settings(
        app_username="qa.user",
        app_password="a-secure-password",
        session_secret="s" * 32,
    )
    application = Starlette(
        routes=[
            Route("/", protected_endpoint, methods=["GET"]),
            Route("/api/protected", protected_endpoint, methods=["POST"]),
        ]
    )
    application.add_middleware(OrganizationHttpMiddleware, settings=settings)
    client = TestClient(application)

    redirect = client.get("/", follow_redirects=False)
    unauthorized_api = client.post("/api/protected")
    client.cookies.set(SESSION_COOKIE, issue_browser_session("qa.user", settings))
    authorized_page = client.get("/")
    authorized_api = client.post("/api/protected")

    assert redirect.status_code == 303
    assert redirect.headers["location"] == "/login"
    assert unauthorized_api.status_code == 401
    assert authorized_page.status_code == 200
    assert authorized_api.status_code == 200


def test_tampered_browser_session_is_rejected() -> None:
    settings = Settings(
        app_username="qa.user",
        app_password="a-secure-password",
        session_secret="s" * 32,
    )
    client = hardened_client(settings)
    client.cookies.set(SESSION_COOKIE, issue_browser_session("qa.user", settings) + "tampered")

    assert client.post("/api/protected").status_code == 401


def test_login_endpoint_sets_http_only_same_site_session(monkeypatch) -> None:
    settings = Settings(
        app_username="qa.user",
        app_password="a-secure-password",
        session_secret="s" * 32,
    )
    monkeypatch.setattr("app.main.settings_at_startup", settings)
    client = TestClient(app)

    invalid = client.post("/api/auth/login", json={"username": "qa.user", "password": "wrong"})
    accepted = client.post(
        "/api/auth/login",
        json={"username": "qa.user", "password": "a-secure-password"},
    )

    assert invalid.status_code == 401
    assert accepted.status_code == 200
    cookie = accepted.headers["set-cookie"]
    assert f"{SESSION_COOKIE}=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie


def test_declared_oversized_request_is_rejected_before_routing() -> None:
    settings = Settings(max_request_body_bytes=2048, max_upload_bytes=1024)
    response = hardened_client(settings).post(
        "/api/protected",
        content=b"x" * 2049,
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body exceeds the configured limit"


def test_production_responses_include_transport_and_browser_protections() -> None:
    settings = Settings(
        environment="production",
        api_auth_token="a" * 32,
        allowed_hosts="service.example.com",
    )
    response = hardened_client(settings).post(
        "/api/protected",
        json={"value": "safe"},
        headers={"Authorization": f"Bearer {settings.api_auth_token_value}"},
    )

    assert response.headers["strict-transport-security"].startswith("max-age=31536000")
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["cross-origin-opener-policy"] == "same-origin"


def test_development_api_docs_allow_only_the_required_swagger_cdn() -> None:
    client = TestClient(app)

    response = client.get("/docs")

    assert response.status_code == 200
    policy = response.headers["content-security-policy"]
    assert "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net" in policy
    assert "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net" in policy
    assert "cdn.jsdelivr.net" not in client.get("/").headers["content-security-policy"]


def test_liveness_and_readiness_are_separate() -> None:
    client = TestClient(app)

    live = client.get("/api/live")
    ready = client.get("/api/ready")

    assert live.status_code == 200
    assert live.json() == {"ok": True}
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert ready.json()["upstream_copilot_checked"] is False
