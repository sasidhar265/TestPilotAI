from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from app.models import GenerateRequest, TestSuite


class AgentCapability(StrEnum):
    REQUIREMENT_TO_TEST_CASE = "requirement-to-test-case"
    TEST_DESIGN = "test-design"
    NORMAL_STEPS = "normal-steps"
    SPECFLOW_BDD = "specflow-bdd"
    STRUCTURED_OUTPUT = "structured-output"


class AgentDescriptor(BaseModel):
    """Stable metadata exposed by an approved runtime adapter."""

    model_config = ConfigDict(frozen=True)

    runtime_id: str
    display_name: str
    capabilities: frozenset[AgentCapability]


@runtime_checkable
class TestDesignAgent(Protocol):
    descriptor: AgentDescriptor

    async def generate(
        self,
        request: GenerateRequest,
        phase: str = "initial",
        existing_titles: list[str] | None = None,
    ) -> TestSuite: ...


@runtime_checkable
class RequirementToTestCaseAgent(Protocol):
    """Agent role that converts normalized requirements into a test suite."""

    descriptor: AgentDescriptor

    async def generate(
        self,
        request: GenerateRequest,
        phase: str = "initial",
        existing_titles: list[str] | None = None,
    ) -> TestSuite: ...
