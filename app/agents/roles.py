"""Discoverable metadata shared by the application's functional agents."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AgentKind(StrEnum):
    INPUT = "input"
    GENERATOR = "test-case-generator"
    VALIDATOR = "validator"
    STORAGE = "test-storage"


class FunctionalAgentDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    kind: AgentKind
    purpose: str
    runtime: str
    capabilities: tuple[str, ...]
