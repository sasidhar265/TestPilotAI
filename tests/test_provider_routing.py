"""Provider routing is explicit; only automatic mode permits cross-provider fallback."""

from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.runner import CopilotGenerationError, StructuredAgentDefinition
from app.config import Settings
from app.models import LlmModel


class ExampleArtifact(BaseModel):
    text: str


DEFINITION = StructuredAgentDefinition(ExampleArtifact, "Timeout", "Empty", "Invalid")


def runner(monkeypatch):
    instance = ArtifactGenerationRunner(
        Settings(
            _env_file=None,
            openai_api_key="test-key",
            gemini_api_key="test-key",
            organizational_memory_enabled=False,
        )
    )
    monkeypatch.setattr("app.agents.artifact_runner.shutil.which", lambda _: "/test/codex")
    calls = {
        LlmModel.OPENAI: AsyncMock(return_value=ExampleArtifact(text="approved")),
        LlmModel.CODEX: AsyncMock(return_value=ExampleArtifact(text="approved")),
        LlmModel.GEMINI: AsyncMock(return_value=ExampleArtifact(text="approved")),
        LlmModel.CLAUDE_HAIKU_4_5: AsyncMock(return_value=ExampleArtifact(text="approved")),
    }
    instance._openai = calls[LlmModel.OPENAI]
    instance._codex = calls[LlmModel.CODEX]
    instance._gemini = calls[LlmModel.GEMINI]
    instance.copilot.generate_structured = calls[LlmModel.CLAUDE_HAIKU_4_5]
    return instance, calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selection", [LlmModel.OPENAI, LlmModel.CODEX, LlmModel.GEMINI, LlmModel.CLAUDE_HAIKU_4_5]
)
async def test_explicit_selection_calls_only_selected_provider(monkeypatch, selection):
    instance, calls = runner(monkeypatch)
    result = await instance.generate_structured(
        DEFINITION, instructions="Policy", prompt="Input", llm_model=selection
    )
    assert result.text == "approved"
    for provider, call in calls.items():
        assert call.await_count == (1 if provider == selection else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", [LlmModel.OPENAI, LlmModel.CODEX])
async def test_explicit_provider_failure_never_calls_copilot(monkeypatch, selection):
    instance, calls = runner(monkeypatch)
    calls[selection].side_effect = CopilotGenerationError("Provider unavailable")
    with pytest.raises(CopilotGenerationError, match="selected generation provider"):
        await instance.generate_structured(
            DEFINITION, instructions="Policy", prompt="Input", llm_model=selection
        )
    for provider, call in calls.items():
        assert call.await_count == (1 if provider == selection else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", [LlmModel.OPENAI, LlmModel.CODEX])
async def test_repairs_stay_on_explicit_provider(monkeypatch, selection):
    instance, calls = runner(monkeypatch)
    calls[selection].side_effect = [ExampleArtifact(text="bad"), ExampleArtifact(text="approved")]

    def validate(output):
        if output.text == "bad":
            raise ValueError("Revise output")
        return output

    result = await instance.generate_structured(
        DEFINITION, instructions="Policy", prompt="Input", llm_model=selection, validate=validate
    )
    assert result.text == "approved"
    for provider, call in calls.items():
        assert call.await_count == (2 if provider == selection else 0)


@pytest.mark.asyncio
async def test_only_auto_fallback_advances_to_another_provider(monkeypatch):
    instance, calls = runner(monkeypatch)
    calls[LlmModel.CLAUDE_HAIKU_4_5].side_effect = CopilotGenerationError("Quota")
    await instance.generate_structured(
        DEFINITION, instructions="Policy", prompt="Input", llm_model=LlmModel.AUTO_FALLBACK
    )
    calls[LlmModel.CLAUDE_HAIKU_4_5].assert_awaited_once()
    calls[LlmModel.OPENAI].assert_awaited_once()
    calls[LlmModel.CODEX].assert_not_awaited()


@pytest.mark.asyncio
async def test_non_policy_copilot_model_is_rejected(monkeypatch):
    instance, calls = runner(monkeypatch)
    with pytest.raises(CopilotGenerationError, match="Copilot requires claude-haiku-4.5"):
        await instance.generate_structured(
            DEFINITION, instructions="Policy", prompt="Input", llm_model=LlmModel.GPT_5_4
        )
    assert all(call.await_count == 0 for call in calls.values())
