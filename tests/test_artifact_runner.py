from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.reqnroll_step_definition_agent import STEP_DEFINITION_AGENT, StepDefinitionArtifact
from app.agents.runner import CopilotGenerationError
from app.config import Settings


def settings(**kwargs):
    return Settings(_env_file=None, codex_executable="test-codex", **kwargs)


def artifact():
    return StepDefinitionArtifact(files=[{"path": "Steps.cs", "content": "class Steps {}"}])


@pytest.mark.asyncio
@respx.mock
async def test_code_generation_fails_over_to_configured_openai() -> None:
    runner = ArtifactGenerationRunner(settings(openai_api_key="test-key"))
    runner.copilot.generate_structured = AsyncMock(side_effect=CopilotGenerationError("quota"))
    route = respx.post("https://api.openai.com/v1/responses").mock(
        return_value=httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": artifact().model_dump_json()}],
                    }
                ]
            },
        )
    )
    result = await runner.generate_structured(
        STEP_DEFINITION_AGENT, instructions="Implement C#", prompt="Approved suite"
    )
    assert result == artifact()
    assert route.called
    assert b'"code_artifact"' in route.calls[0].request.content
    assert b'"store":false' in route.calls[0].request.content


@pytest.mark.asyncio
@respx.mock
async def test_code_generation_fails_over_to_codex_after_openai_quota(monkeypatch) -> None:
    runner = ArtifactGenerationRunner(settings(openai_api_key="test-key"))
    runner.copilot.generate_structured = AsyncMock(side_effect=CopilotGenerationError("quota"))
    respx.post("https://api.openai.com/v1/responses").mock(return_value=httpx.Response(429))
    monkeypatch.setattr("app.agents.artifact_runner.shutil.which", lambda _: "/test/codex")
    runner._codex = AsyncMock(return_value=artifact())
    assert (
        await runner.generate_structured(
            STEP_DEFINITION_AGENT, instructions="Implement C#", prompt="Approved suite"
        )
        == artifact()
    )
    runner._codex.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_configured_provider_returns_an_error_without_source(monkeypatch) -> None:
    runner = ArtifactGenerationRunner(settings())
    runner.copilot.generate_structured = AsyncMock(side_effect=CopilotGenerationError("quota"))
    monkeypatch.setattr("app.agents.artifact_runner.shutil.which", lambda _: None)
    with pytest.raises(CopilotGenerationError, match="github-copilot: quota"):
        await runner.generate_structured(STEP_DEFINITION_AGENT, instructions="C#", prompt="suite")


@pytest.mark.asyncio
async def test_codex_uses_read_only_structured_artifact_output(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.artifact_runner.shutil.which", lambda _: "/test/codex")
    process = AsyncMock()
    process.returncode = 0
    monkeypatch.setattr("app.agents.artifact_runner.stop_process_tree", AsyncMock())
    process.communicate.return_value = (artifact().model_dump_json().encode(), b"")
    spawn = AsyncMock(return_value=process)
    monkeypatch.setattr("app.agents.artifact_runner.asyncio.create_subprocess_exec", spawn)
    result = await ArtifactGenerationRunner(settings())._codex(STEP_DEFINITION_AGENT, "C#", "suite")
    assert result == artifact()
    args = spawn.call_args.args
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--output-schema" in args
    assert "--ephemeral" in args


@pytest.mark.asyncio
async def test_codex_timeout_terminates_process(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.artifact_runner.shutil.which", lambda _: "/test/codex")
    process = AsyncMock()
    process.returncode = None
    process.communicate.side_effect = TimeoutError
    from unittest.mock import Mock

    process.kill = Mock()
    cleanup = AsyncMock()
    monkeypatch.setattr("app.agents.artifact_runner.stop_process_tree", cleanup)
    monkeypatch.setattr(
        "app.agents.artifact_runner.asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    )
    import asyncio

    wait_for = AsyncMock(wraps=asyncio.wait_for)
    monkeypatch.setattr("app.agents.artifact_runner.asyncio.wait_for", wait_for)
    with pytest.raises(CopilotGenerationError, match="timed out after 900 seconds"):
        await ArtifactGenerationRunner(
            settings(codex_timeout_seconds=30, codex_artifact_timeout_seconds=900)
        )._codex(STEP_DEFINITION_AGENT, "C#", "suite")
    assert wait_for.call_args.kwargs["timeout"] == 900
    cleanup.assert_awaited_once_with(process)


def require_implemented(value):
    if value.files[0].content == "incomplete":
        raise ValueError("Missing Then implementation; configure approved oracle data.")
    return value


@pytest.mark.asyncio
async def test_incomplete_json_repairs_then_falls_over_to_next_provider(monkeypatch) -> None:
    runner = ArtifactGenerationRunner(settings(openai_api_key="test-key"))
    incomplete = artifact()
    incomplete.files[0].content = "incomplete"
    runner.copilot.generate_structured = AsyncMock(return_value=incomplete)
    runner._openai = AsyncMock(return_value=artifact())
    runner._codex = AsyncMock()
    monkeypatch.setattr("app.agents.artifact_runner.shutil.which", lambda _: "/test/codex")
    result = await runner.generate_structured(
        STEP_DEFINITION_AGENT,
        instructions="Implement C#",
        prompt="Approved suite",
        validate=require_implemented,
    )
    assert result == artifact()
    assert runner.copilot.generate_structured.await_count == 2
    repair = runner.copilot.generate_structured.call_args.kwargs["prompt"]
    assert "IMPLEMENTATION REVIEW" in repair
    assert "Missing Then implementation" in repair
    runner._openai.assert_awaited_once()
    runner._codex.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_provider_is_not_retried_during_fallback_repair(monkeypatch) -> None:
    runner = ArtifactGenerationRunner(settings(openai_api_key="test-key"))
    incomplete = artifact()
    incomplete.files[0].content = "incomplete"
    runner.copilot.generate_structured = AsyncMock(side_effect=CopilotGenerationError("quota"))
    runner._openai = AsyncMock(side_effect=[incomplete, artifact()])
    monkeypatch.setattr("app.agents.artifact_runner.shutil.which", lambda _: None)
    assert (
        await runner.generate_structured(
            STEP_DEFINITION_AGENT,
            instructions="C#",
            prompt="suite",
            validate=require_implemented,
        )
        == artifact()
    )
    runner.copilot.generate_structured.assert_awaited_once()
    assert runner._openai.await_count == 2


@pytest.mark.asyncio
async def test_all_incomplete_providers_preserve_actionable_failure(monkeypatch) -> None:
    runner = ArtifactGenerationRunner(settings(openai_api_key="test-key"))
    incomplete = artifact()
    incomplete.files[0].content = "incomplete"
    runner.copilot.generate_structured = AsyncMock(return_value=incomplete)
    runner._openai = AsyncMock(return_value=incomplete)
    runner._codex = AsyncMock(return_value=incomplete)
    monkeypatch.setattr("app.agents.artifact_runner.shutil.which", lambda _: "/test/codex")
    with pytest.raises(
        ValueError, match="failed validation after repair attempts.*approved oracle data"
    ):
        await runner.generate_structured(
            STEP_DEFINITION_AGENT,
            instructions="C#",
            prompt="suite",
            validate=require_implemented,
        )
    assert runner.copilot.generate_structured.await_count == 2
    assert runner._openai.await_count == 2
    assert runner._codex.await_count == 2


@pytest.mark.asyncio
async def test_incomplete_bindings_keep_diagnostics_out_of_user_error(monkeypatch, caplog):
    from app.agents.reqnroll_validation import IncompleteImplementationError

    runner = ArtifactGenerationRunner(settings())
    runner.copilot.generate_structured = AsyncMock(return_value=artifact())
    monkeypatch.setattr("app.agents.artifact_runner.shutil.which", lambda _: None)
    findings = [f"No Given binding implementation for: Given fixture {i}" for i in range(31)]

    def reject(value):
        raise IncompleteImplementationError(findings, ["Provider rejected an earlier draft."], 31)

    with pytest.raises(ValueError, match="31 required steps") as error:
        await runner.generate_structured(
            STEP_DEFINITION_AGENT, instructions="C#", prompt="suite", validate=reject
        )
    assert len(str(error.value)) < 600
    assert "No Given binding" not in str(error.value)
    assert "Provider rejected" not in str(error.value)
    repair = runner.copilot.generate_structured.call_args.kwargs["prompt"]
    assert findings[-1] in repair
    assert "Provider rejected an earlier draft." in repair
    record = next(r for r in caplog.records if r.message == "artifact_implementation_rejected")
    assert findings[-1] in record.event_details["findings"]
