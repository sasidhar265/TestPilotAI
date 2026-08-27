"""Discoverable metadata shared by the application's functional agents."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AgentKind(StrEnum):
    INPUT = "input"
    ROUTER = "specforge-router"
    MANUAL_GENERATOR = "manual-test-generator"
    AUTOMATION_GENERATOR = "automation-test-generator"
    VALIDATOR = "validator"
    CONTEXT_CONVERTER = "context-converter"
    OUTPUT = "output"
    STORAGE = "test-storage"


class FunctionalAgentDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    kind: AgentKind
    purpose: str
    runtime: str
    capabilities: tuple[str, ...]
    instruction_file: str | None = None
