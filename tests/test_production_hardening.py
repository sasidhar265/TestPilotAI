import pytest
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

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


def test_coordinator_timeout_covers_at_least_one_specialist_timeout() -> None:
    with pytest.raises(ValidationError, match="COPILOT_COORDINATOR_TIMEOUT_SECONDS"):
        Settings(copilot_timeout_seconds=300, copilot_coordinator_timeout_seconds=299)


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


def test_liveness_and_readiness_are_separate() -> None:
    client = TestClient(app)

    live = client.get("/api/live")
    ready = client.get("/api/ready")

    assert live.status_code == 200
    assert live.json() == {"ok": True}
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert ready.json()["upstream_copilot_checked"] is False
