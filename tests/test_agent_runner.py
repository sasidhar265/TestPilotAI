from pathlib import Path

import pytest
from pydantic import BaseModel

from app.agents.runner import (
    CopilotAgentRunner,
    CopilotGenerationError,
    StructuredAgentDefinition,
    _provider_failure_message,
)
from app.config import Settings


class ExampleArtifact(BaseModel):
    value: str


DEFINITION = StructuredAgentDefinition(
    output_model=ExampleArtifact,
    timeout_error="timed out",
    empty_error="empty",
    invalid_error="invalid",
)


class StubRunner(CopilotAgentRunner):
    def __init__(self, content: str) -> None:
        super().__init__(Settings())
        self.content = content

    async def invoke(self, **_: object) -> str:
        return self.content


class SequenceRunner(CopilotAgentRunner):
    def __init__(self, contents: list[str]) -> None:
        super().__init__(Settings())
        self.contents = iter(contents)
        self.prompts: list[str] = []
        self.instructions: list[str] = []

    async def invoke(self, **arguments: object) -> str:
        self.prompts.append(str(arguments["prompt"]))
        self.instructions.append(str(arguments["instructions"]))
        content = next(self.contents)
        if not content:
            raise CopilotGenerationError(str(arguments["empty_error"]))
        return content


@pytest.mark.asyncio
async def test_structured_runner_validates_declared_output_model() -> None:
    artifact = await StubRunner('```json\n{"value":"ready"}\n```').generate_structured(
        DEFINITION,
        instructions="Agent policy",
        prompt="Request",
    )

    assert artifact == ExampleArtifact(value="ready")


@pytest.mark.asyncio
async def test_structured_runner_returns_agent_specific_safe_schema_error() -> None:
    with pytest.raises(CopilotGenerationError, match="Automatic schema repair"):
        await StubRunner('{"unexpected":true}').generate_structured(
            DEFINITION,
            instructions="Agent policy",
            prompt="Request",
        )


@pytest.mark.asyncio
async def test_structured_runner_repairs_invalid_provider_output_once() -> None:
    runner = SequenceRunner(['{"unexpected":true}', '{"value":"repaired"}'])

    artifact = await runner.generate_structured(
        DEFINITION,
        instructions="Agent policy",
        prompt="Original request",
    )

    assert artifact == ExampleArtifact(value="repaired")
    assert len(runner.prompts) == 2
    assert "INVALID FIELD LOCATIONS" in runner.prompts[1]
    assert '"value"' in runner.prompts[1]


@pytest.mark.asyncio
async def test_structured_runner_retries_an_empty_provider_session_once() -> None:
    runner = SequenceRunner(["", '{"value":"available after retry"}'])

    artifact = await runner.generate_structured(
        DEFINITION,
        instructions="Agent policy",
        prompt="Original request",
    )

    assert artifact == ExampleArtifact(value="available after retry")
    assert len(runner.prompts) == 2
    assert "RETRY REQUIREMENT" in runner.prompts[1]
    assert "Agent policy" in runner.instructions[1]
    assert "Generate a complete test suite" not in runner.instructions[1]


def test_copilot_session_lifecycle_has_one_python_owner() -> None:
    application_root = Path(__file__).parent.parent / "app"
    owners = [
        path.relative_to(application_root).as_posix()
        for path in application_root.rglob("*.py")
        if "create_session(" in path.read_text(encoding="utf-8")
    ]

    assert owners == ["agents/runner.py"]


def test_provider_quota_failure_has_actionable_message() -> None:
    message = _provider_failure_message({"status": 402, "code": "quota_exceeded", "type": "quota"})

    assert "quota is exhausted" in message
    assert "eligible model/account" in message


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["construct", "enter", "session", "send", "exit"])
async def test_sdk_runtime_failures_are_safe_provider_errors(failure_point):
    from unittest.mock import AsyncMock, Mock

    raw = RuntimeError("runtime unavailable: secret-token")
    client = AsyncMock()
    client.__aenter__.return_value = client
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.on = Mock()
    client.create_session.return_value = session
    factory = Mock(return_value=client)
    failures = {
        "construct": factory,
        "enter": client.__aenter__,
        "session": client.create_session,
        "send": session.send,
        "exit": session.__aexit__,
    }
    failures[failure_point].side_effect = raw
    runner = CopilotAgentRunner(Settings(_env_file=None), factory)
    # Exit failure occurs after the response wait; avoid waiting on an SDK event.
    if failure_point == "exit":
        session.send.side_effect = CopilotGenerationError("empty")
    with pytest.raises(CopilotGenerationError, match="runtime could not start") as error:
        await runner.invoke(instructions="policy", prompt="source", timeout_error="timeout")
    assert "secret-token" not in str(error.value)
    assert error.value.__cause__ is raw


@pytest.mark.asyncio
async def test_sdk_cancellation_remains_cancellable():
    import asyncio
    from unittest.mock import Mock

    factory = Mock(side_effect=asyncio.CancelledError())
    runner = CopilotAgentRunner(Settings(_env_file=None), factory)
    with pytest.raises(asyncio.CancelledError):
        await runner.invoke(instructions="policy", prompt="source", timeout_error="timeout")
