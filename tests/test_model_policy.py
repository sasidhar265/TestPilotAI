from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent_instructions import AGENT_FILES, load_agent_instructions
from app.agents.runner import CopilotAgentRunner, CopilotGenerationError
from app.config import Settings
from app.generator import CodexGenerator, CopilotGenerator
from app.model_policy import CODEX_MODEL, COPILOT_MODEL
from app.models import GenerateRequest, LlmModel
from app.services.model_access import _copilot_access_result


@pytest.mark.parametrize("override", ["", "auto", "gpt-5.4", "other-model"])
def test_environment_cannot_override_mandatory_models(monkeypatch, override):
    monkeypatch.setenv("CODEX_MODEL", override)
    monkeypatch.setenv("COPILOT_MODEL", override)
    settings = Settings(_env_file=None)
    assert settings.codex_model == CODEX_MODEL
    assert settings.copilot_model == COPILOT_MODEL


@pytest.mark.asyncio
async def test_copilot_session_pins_model_even_after_unvalidated_settings_copy():
    settings = Settings(_env_file=None).model_copy(update={"copilot_model": "other-model"})
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.create_session.side_effect = RuntimeError("stop before generation")
    runner = CopilotAgentRunner(settings, lambda **kwargs: client)
    with pytest.raises(CopilotGenerationError, match="runtime could not start"):
        await runner.invoke(instructions="test", prompt="test", timeout_error="timeout")
    assert client.create_session.call_args.kwargs["model"] == COPILOT_MODEL


@pytest.mark.asyncio
async def test_codex_suite_command_pins_astra(monkeypatch):
    monkeypatch.setattr("app.generator.shutil.which", lambda _: "/test/codex")
    spawn = AsyncMock(side_effect=OSError("stop before generation"))
    monkeypatch.setattr("app.generator.asyncio.create_subprocess_exec", spawn)
    settings = Settings(_env_file=None).model_copy(update={"codex_model": "other-model"})
    with pytest.raises(CopilotGenerationError):
        await CodexGenerator(settings).generate(
            GenerateRequest(description="Generate quotation tests", llm_model=LlmModel.CODEX)
        )
    command = spawn.call_args.args
    assert command[command.index("--model") + 1] == CODEX_MODEL


@pytest.mark.asyncio
async def test_explicit_alternative_copilot_model_is_rejected():
    with pytest.raises(CopilotGenerationError, match="requires claude-haiku-4.5"):
        await CopilotGenerator(Settings(_env_file=None)).generate(
            GenerateRequest(description="Generate quotation tests", llm_model=LlmModel.GPT_5_4)
        )


@pytest.mark.parametrize("route", ["auto", "organization-default", COPILOT_MODEL])
def test_copilot_alias_requires_haiku_access(route):
    other = SimpleNamespace(id="gpt-5.4", name="Other", policy=None, billing=None)
    quota = SimpleNamespace(quota_snapshots={})
    assert not _copilot_access_result([other], quota, route)["can_use"]
    haiku = SimpleNamespace(id=COPILOT_MODEL, name="Claude Haiku 4.5", policy=None, billing=None)
    assert _copilot_access_result([other, haiku], quota, route)["can_use"]
    assert not _copilot_access_result([other, haiku], quota, "gpt-5.4")["can_use"]


@pytest.mark.parametrize("agent", AGENT_FILES)
def test_all_agent_instructions_include_model_policy(agent):
    instructions = load_agent_instructions(agent)
    assert CODEX_MODEL in instructions
    assert COPILOT_MODEL in instructions
