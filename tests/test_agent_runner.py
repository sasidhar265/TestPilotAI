from pathlib import Path

import pytest
from pydantic import BaseModel

from app.agents.runner import (
    CopilotAgentRunner,
    CopilotGenerationError,
    StructuredAgentDefinition,
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
    with pytest.raises(CopilotGenerationError, match="invalid"):
        await StubRunner('{"unexpected":true}').generate_structured(
            DEFINITION,
            instructions="Agent policy",
            prompt="Request",
        )


def test_copilot_session_lifecycle_has_one_python_owner() -> None:
    application_root = Path(__file__).parent.parent / "app"
    owners = [
        path.relative_to(application_root).as_posix()
        for path in application_root.rglob("*.py")
        if "create_session(" in path.read_text(encoding="utf-8")
    ]

    assert owners == ["agents/runner.py"]
