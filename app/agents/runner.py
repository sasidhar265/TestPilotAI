"""Shared GitHub Copilot session and structured-output runtime for Markdown agents."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class CopilotGenerationError(RuntimeError):
    """A safe, user-facing failure produced by a Copilot-backed agent."""


class CopilotTimeoutError(CopilotGenerationError):
    """A bounded Copilot session exceeded its configured execution budget."""


@dataclass(frozen=True)
class StructuredAgentDefinition(Generic[OutputModel]):
    """Declarative executable contract paired with repository-owned Markdown policy."""

    output_model: type[OutputModel]
    timeout_error: str
    empty_error: str
    invalid_error: str


def json_object(content: str) -> str:
    """Extract one JSON object while tolerating an accidental Markdown fence."""
    value = content.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            value = "\n".join(lines[1:-1]).strip()
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object found")
    return value[start : end + 1]


class CopilotAgentRunner:
    """Own common SDK lifecycle, safe configuration, events, and schema validation."""

    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory

    async def invoke(
        self,
        *,
        instructions: str,
        prompt: str,
        timeout_error: str,
        empty_error: str | None = None,
        tools: list[Any] | None = None,
        capture_response: bool = True,
        timeout_seconds: float | None = None,
    ) -> str | None:
        """Run one isolated Markdown-directed Copilot session."""
        try:
            from copilot import CopilotClient
            from copilot.session_events import AssistantMessageData, SessionIdleData
        except ImportError as error:
            raise CopilotGenerationError(
                "GitHub Copilot SDK is not installed. Run 'pip install -e .' and restart."
            ) from error

        factory = self.client_factory or CopilotClient
        client_options: dict[str, Any] = {
            "working_directory": str(self.settings.copilot_working_directory),
            "use_logged_in_user": not bool(self.settings.copilot_github_token),
            "mode": "copilot-cli",
        }
        if self.settings.copilot_github_token:
            client_options["github_token"] = self.settings.copilot_github_token

        supplied_tools = tools or []
        session_options: dict[str, Any] = {
            "system_message": {"mode": "append", "content": instructions},
            "streaming": False,
            "infinite_sessions": {"enabled": False},
            "available_tools": [tool.name for tool in supplied_tools],
            "skip_custom_instructions": True,
            "enable_config_discovery": False,
            "enable_skills": False,
            "enable_session_store": False,
            "memory": {"enabled": False},
            "enable_file_hooks": False,
            "enable_host_git_operations": False,
            "mcp_servers": {},
        }
        if supplied_tools:
            session_options["tools"] = supplied_tools
        if self.settings.copilot_model:
            session_options["model"] = self.settings.copilot_model

        content: str | None = None
        idle = asyncio.Event()
        async with factory(**client_options) as client:
            async with await client.create_session(**session_options) as session:

                def on_event(event: Any) -> None:
                    nonlocal content
                    data = getattr(event, "data", None)
                    if capture_response and isinstance(data, AssistantMessageData):
                        content = data.content
                    elif isinstance(data, SessionIdleData):
                        idle.set()

                session.on(on_event)
                await session.send(prompt)
                try:
                    await asyncio.wait_for(
                        idle.wait(),
                        timeout_seconds or self.settings.copilot_timeout_seconds,
                    )
                except TimeoutError as error:
                    raise CopilotTimeoutError(timeout_error) from error

        if capture_response and not content:
            raise CopilotGenerationError(empty_error or "GitHub Copilot returned no output.")
        return content

    async def generate_structured(
        self,
        definition: StructuredAgentDefinition[OutputModel],
        *,
        instructions: str,
        prompt: str,
        normalize: Callable[[Any], Any] | None = None,
    ) -> OutputModel:
        """Invoke an agent and validate its JSON against the declared Pydantic contract."""
        content = await self.invoke(
            instructions=instructions,
            prompt=prompt,
            timeout_error=definition.timeout_error,
            empty_error=definition.empty_error,
        )
        try:
            payload = json.loads(json_object(content or ""))
            if normalize is not None:
                payload = normalize(payload)
            return definition.output_model.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as error:
            raise CopilotGenerationError(definition.invalid_error) from error
