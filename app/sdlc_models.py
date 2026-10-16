"""Typed contracts for autonomous SDLC stage agents and executable handoffs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import GenerateRequest, LlmModel

AgentStage = Literal[
    "planning", "requirements", "design", "development", "testing", "release", "operations"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeliveryStart(StrictModel):
    requirements_version: int = Field(ge=1)
    target: Literal["design", "tested", "staging", "production"] = "design"


class DeliveryMission(StrictModel):
    requirements_version: int | None = Field(default=None, ge=1)
    brief: str = Field(min_length=10, max_length=30000)
    constraints: str = Field(default="", max_length=100000)
    source_request: GenerateRequest | None = None
    llm_model: LlmModel = LlmModel.CODEX
    target: Literal["design", "tested", "staging", "production"] = "design"


class AgentTask(StrictModel):
    id: str = Field(min_length=2, max_length=60)
    title: str = Field(min_length=5, max_length=300)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=30)
    depends_on: list[str] = Field(default_factory=list, max_length=30)
    requirement_refs: list[str] = Field(default_factory=list, max_length=100)


class AgentDocument(StrictModel):
    title: str = Field(min_length=5, max_length=200)
    summary: str = Field(min_length=20, max_length=4000)
    document: str = Field(min_length=40, max_length=100000)
    tasks: list[AgentTask] = Field(min_length=1, max_length=100)
    risks: list[str] = Field(default_factory=list, max_length=50)
    blockers: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def consistent_tasks(self) -> "AgentDocument":
        ids = {task.id for task in self.tasks}
        if len(ids) != len(self.tasks):
            raise ValueError("Task IDs must be unique")
        pending = {task.id: set(task.depends_on) for task in self.tasks}
        if any(not dependencies <= ids for dependencies in pending.values()):
            raise ValueError("Task dependencies must refer to known task IDs")
        resolved: set[str] = set()
        while pending:
            ready = {
                identifier
                for identifier, dependencies in pending.items()
                if dependencies <= resolved
            }
            if not ready:
                raise ValueError("Task dependencies contain a cycle")
            resolved.update(ready)
            pending = {
                identifier: dependencies
                for identifier, dependencies in pending.items()
                if identifier not in ready
            }
        return self


class SourceFile(StrictModel):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=300000)


class Implementation(StrictModel):
    summary: str = Field(min_length=20, max_length=4000)
    files: list[SourceFile] = Field(min_length=1, max_length=100)
    requirements_covered: list[str] = Field(min_length=1, max_length=100)
    blockers: list[str] = Field(default_factory=list, max_length=50)


class CodeReview(StrictModel):
    passed: bool
    summary: str = Field(min_length=20, max_length=4000)
    blocking_findings: list[str] = Field(default_factory=list, max_length=50)
    findings: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def no_false_pass(self) -> "CodeReview":
        if self.passed and self.blocking_findings:
            raise ValueError("A code review with blocking findings cannot pass")
        return self
