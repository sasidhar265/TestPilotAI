import asyncio

import pytest
from pydantic import SecretStr, ValidationError

from app.auth import issue_browser_session, session_username
from app.config import Settings
from app.services import model_access


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
