import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from app.agents.runner import CopilotGenerationError
from app.config import Settings
from app.generator import FallbackGenerator, GeminiGenerator
from app.models import GenerateRequest, GenerationSource
from app.services.model_access import available_model_options, failure_reason, inspect_model_access


@pytest.fixture
def settings():
    return Settings(_env_file=None, gemini_api_key=SecretStr("gemini-private-key"))


@pytest.fixture
def payload():
    return {
        "feature_name": "Login",
        "test_cases": [
            {
                "id": "TC-001",
                "title": "Valid login",
                "objective": "Verify login",
                "category": "smoke",
                "priority": "P1",
                "execution_mode": "manual",
                "feasibility_reason": "Review login behavior",
                "steps": [
                    {"action": "Submit valid credentials", "expected_result": "Dashboard opens"}
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_generation_validates_and_records_source(monkeypatch, settings, payload):
    async def post(client, url, **kwargs):
        assert url.endswith(f"/models/{settings.gemini_model}:generateContent")
        assert "gemini-private-key" not in url
        assert kwargs["headers"]["x-goog-api-key"] == "gemini-private-key"
        body = kwargs["json"]
        assert body["generationConfig"]["responseFormat"]["text"]["schema"]["properties"]
        assert body["systemInstruction"]["parts"][0]["text"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"thought": True, "text": "ignore reasoning"},
                                {"text": json.dumps(payload)},
                            ]
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    suite = await GeminiGenerator(settings).generate(
        GenerateRequest(description="As a user I can log in with valid credentials.")
    )
    assert suite.generation_source == GenerationSource.GEMINI
    assert suite.test_cases[0].title == "Valid login"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body",
    [
        (401, {}),
        (403, {}),
        (429, {}),
        (500, {}),
        (200, {}),
        (200, {"candidates": []}),
        (200, {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
        (200, {"candidates": [{"finishReason": "SAFETY"}]}),
        (200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "{}"}]}}]}),
    ],
)
async def test_invalid_and_failed_responses(monkeypatch, settings, status, body):
    async def post(client, url, **kwargs):
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with pytest.raises(CopilotGenerationError) as error:
        await GeminiGenerator(settings).generate(GenerateRequest(description="Verify user login."))
    assert "gemini-private-key" not in str(error.value)


@pytest.mark.asyncio
async def test_missing_key():
    with pytest.raises(CopilotGenerationError, match="GEMINI_API_KEY"):
        await GeminiGenerator(Settings(_env_file=None)).generate(
            GenerateRequest(description="Verify user login.")
        )


@pytest.mark.asyncio
async def test_explicit_and_fallback_routes(settings):
    generator = FallbackGenerator(settings)
    generator.copilot.generate = AsyncMock(side_effect=CopilotGenerationError("unavailable"))
    generator.openai.generate = AsyncMock(side_effect=CopilotGenerationError("unavailable"))
    generator.gemini.generate = AsyncMock(return_value="gemini-suite")
    generator.codex.generate = AsyncMock()
    request = GenerateRequest(description="Verify user login.", llm_model="gemini")
    assert await generator.generate(request) == "gemini-suite"
    generator.copilot.generate.assert_not_called()
    assert (
        await generator.generate(request.model_copy(update={"llm_model": "auto-fallback"}))
        == "gemini-suite"
    )
    generator.codex.generate.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("methods,expected", [(["generateContent"], True), ([], False)])
async def test_access_check_and_picker(monkeypatch, settings, methods, expected):
    async def get(client, url, **kwargs):
        assert kwargs["headers"]["x-goog-api-key"] == "gemini-private-key"
        return httpx.Response(
            200, json={"supportedGenerationMethods": methods}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    result = await inspect_model_access(settings, "gemini")
    assert result["can_use"] is expected
    from app.services import model_access

    monkeypatch.setattr(model_access, "_inspect_copilot_inventory", AsyncMock(return_value=[]))
    monkeypatch.setattr(model_access, "_inspect_codex", AsyncMock(return_value={"can_use": False}))
    options = await available_model_options(settings)
    assert ("gemini" in [option["model"] for option in options]) is expected


def test_redacts_gemini_key(settings):
    assert "gemini-private-key" not in failure_reason(settings, RuntimeError("gemini-private-key"))
