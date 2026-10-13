import asyncio
import base64
import hashlib
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.auth import issue_browser_session, session_username
from app.config import Settings
from app.services import model_access


def test_domain_guide_csp_allows_exact_script_without_relaxing_other_pages() -> None:
    from starlette.applications import Starlette
    from starlette.responses import FileResponse
    from starlette.routing import Mount, Route
    from starlette.staticfiles import StaticFiles
    from starlette.testclient import TestClient

    from app.observability import OrganizationHttpMiddleware

    guide = Path(__file__).parents[1] / "app/static/auto-finance-uk.html"

    async def page(request):
        return FileResponse(guide)

    app = Starlette(
        routes=[Mount("/static", StaticFiles(directory=guide.parent)), Route("/knowledge", page)]
    )
    app.add_middleware(
        OrganizationHttpMiddleware,
        settings=Settings(_env_file=None, api_auth_token=SecretStr("guide-test-token")),
    )
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer guide-test-token"}
        response = client.get("/static/auto-finance-uk.html", headers=headers)
        assert response.status_code == 200
        script = response.text.partition("<script>")[2].partition("</script>")[0]
        digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        policy = response.headers["content-security-policy"]
        assert f"script-src 'self' 'sha256-{digest}'" in policy
        assert "frame-ancestors 'self'" in policy
        assert response.headers["x-frame-options"] == "SAMEORIGIN"
        assert "'unsafe-inline'" not in policy.split("script-src ")[1].split(";")[0]
        cached = client.get(
            "/static/auto-finance-uk.html",
            headers=headers | {"If-None-Match": response.headers["etag"]},
        )
        assert cached.status_code == 304
        assert cached.headers["content-security-policy"] == policy
        ordinary = client.get("/knowledge", headers=headers)
        assert "script-src 'self';" in ordinary.headers["content-security-policy"]
        assert "sha256-" not in ordinary.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in ordinary.headers["content-security-policy"]
        assert ordinary.headers["x-frame-options"] == "DENY"


def test_provider_diagnostics_redact_all_provider_credentials() -> None:
    settings = Settings(
        _env_file=None,
        copilot_github_token="gh-secret",
        openai_api_key=SecretStr("openai-secret"),
        gemini_api_key=SecretStr("gemini-secret"),
        api_auth_token=SecretStr("auth-secret"),
        app_password=SecretStr("password-secret"),
        session_secret=SecretStr("session-secret"),
        jira_api_token="jira-secret",
    )

    diagnostic = model_access.failure_reason(
        settings,
        RuntimeError(
            "gh-secret openai-secret gemini-secret auth-secret password-secret "
            "session-secret jira-secret Bearer bearer-secret"
        ),
    )

    for credential in (
        "gh-secret",
        "openai-secret",
        "gemini-secret",
        "auth-secret",
        "password-secret",
        "session-secret",
        "jira-secret",
        "bearer-secret",
    ):
        assert credential not in diagnostic
    assert "[redacted]" in diagnostic


def test_expired_or_tampered_browser_session_cannot_be_reused() -> None:
    settings = Settings(
        _env_file=None,
        app_username="qa.user",
        app_password=SecretStr("a-secure-password"),
        session_secret=SecretStr("s" * 32),
    )
    session = issue_browser_session("qa.user", settings)

    assert session_username(session, settings) == "qa.user"
    assert session_username(session + "tampered", settings) is None


def test_resource_limits_reject_unbounded_generation_configuration() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_concurrent_requests=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_concurrent_generations=0)


@pytest.mark.asyncio
async def test_model_access_checks_run_concurrently() -> None:
    started: set[str] = set()
    release = asyncio.Event()

    async def check(settings: Settings, model: str) -> dict[str, object]:
        started.add(model)
        if {"openai", "gemini", "codex"}.issubset(started):
            release.set()
        await asyncio.wait_for(release.wait(), timeout=0.2)
        return model_access._access_result(model, model, model == "gemini", "checked", "ready")

    original = model_access.inspect_model_access
    model_access.inspect_model_access = check
    try:
        result = await model_access.available_model_options(Settings(_env_file=None))
    finally:
        model_access.inspect_model_access = original

    assert {"openai", "gemini", "codex"}.issubset(started)
    assert [option["model"] for option in result] == ["auto-fallback", "gemini"]
