import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services import model_access


@pytest.mark.asyncio
async def test_provider_failure_survives_individual_and_fallback_checks(monkeypatch):
    async def fail(*args):
        raise RuntimeError("models.list failed: Not authenticated. Please authenticate first.")

    async def ready(*args):
        return {"can_use": True, "reason": "Signed in", "display_name": "Codex CLI"}

    monkeypatch.setattr(model_access, "_inspect_copilot", fail)
    monkeypatch.setattr(model_access, "_inspect_codex", ready)
    settings = Settings(_env_file=None, openai_api_key=SecretStr(""))
    result = await model_access.inspect_model_access(settings, "organization-default")
    assert not result["can_use"]
    assert "models.list failed: Not authenticated" in result["reason"]
    fallback = await model_access.inspect_model_access(settings, "auto-fallback")
    assert fallback["can_use"]
    assert fallback["providers"][0]["reason"] == result["reason"]


def test_diagnostics_redact_credentials():
    settings = Settings(_env_file=None, copilot_github_token="private-token")
    reason = model_access.failure_reason(
        settings, RuntimeError("Denied private-token Bearer abc123 github_pat_abcdef sk-secret")
    )
    for secret in ("private-token", "abc123", "github_pat_abcdef", "sk-secret"):
        assert secret not in reason
    assert "Denied" in reason


@pytest.mark.asyncio
async def test_openai_failure_includes_status_and_provider_reason(monkeypatch):
    async def get(*args, **kwargs):
        return httpx.Response(
            403,
            json={"error": {"message": "Project lacks model permission"}},
            request=httpx.Request("GET", "https://example.com/models/test"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    settings = Settings(_env_file=None, openai_api_key=SecretStr("test-key"))
    result = await model_access.inspect_model_access(settings, "openai")
    assert not result["can_use"]
    assert "HTTP 403" in result["reason"]
    assert "Project lacks model permission" in result["reason"]


@pytest.mark.asyncio
async def test_network_failure_is_reported(monkeypatch):
    async def fail(*args):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(model_access, "_inspect_openai", fail)
    result = await model_access.inspect_model_access(Settings(_env_file=None), "openai")
    assert not result["can_use"]
    assert "Connection refused" in result["reason"]
