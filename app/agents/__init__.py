"""Agent runtime contracts, discoverable metadata, and registration policy."""

import sys
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from app.memory import OrganizationalMemory
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


class AgentKind(StrEnum):
    INPUT = "input"
    BUSINESS_RULES = "business-rules"
    KNOWLEDGE = "knowledge"
    QA_MASTER = "qa-master"
    SPECFORGE = "specforge"
    ROUTER = "qa-master"  # Backward-compatible enum alias.
    MANUAL_GENERATOR = "manual-test-generator"
    AUTOMATION_GENERATOR = "automation-test-generator"
    VALIDATOR = "validator"
    CONTEXT_CONVERTER = "context-converter"
    OUTPUT = "output"
    STORAGE = "test-storage"
    TEST_DATA = "test-data"
    EXECUTION = "execution"
    BUG_REPORTER = "bug-reporter"
    METRICS = "metrics"


class FunctionalAgentDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    kind: AgentKind
    purpose: str
    runtime: str
    capabilities: tuple[str, ...]
    instruction_file: str | None = None


class AgentRegistry:
    """Fail-closed registry for organization-approved agent runtimes."""

    APPROVED_RUNTIME = "github-copilot"

    def __init__(self, agent: TestDesignAgent) -> None:
        if agent.descriptor.runtime_id != self.APPROVED_RUNTIME:
            raise ValueError(
                f"Runtime {agent.descriptor.runtime_id!r} is not approved; "
                f"only {self.APPROVED_RUNTIME!r} is allowed."
            )
        self._agent = agent

    def get_test_design_agent(self) -> TestDesignAgent:
        return self._agent

    def get_requirement_to_test_case_agent(self) -> RequirementToTestCaseAgent:
        """Return the approved runtime only when it declares conversion support."""
        capability = AgentCapability.REQUIREMENT_TO_TEST_CASE
        if capability not in self._agent.descriptor.capabilities:
            raise LookupError(
                f"Approved runtime {self.runtime_id!r} does not provide {capability.value!r}."
            )
        return self._agent

    @property
    def runtime_id(self) -> str:
        return self._agent.descriptor.runtime_id


class TestStorageAgent:
    """Retrieve and store validated suites for future exact-match reuse."""

    descriptor = FunctionalAgentDescriptor(
        id="test-storage-agent",
        name="Test Storage Agent",
        kind=AgentKind.STORAGE,
        purpose="Retrieve and store validated suites for future exact-match reuse.",
        runtime="local-sqlite",
        capabilities=("exact-match-retrieval", "validated-suite-storage", "usage-counting"),
    )

    def __init__(self, memory: OrganizationalMemory) -> None:
        self.memory = memory

    def find(self, request: GenerateRequest) -> TestSuite | None:
        return self.memory.get(request)

    def store(self, request: GenerateRequest, suite: TestSuite) -> TestSuite:
        return self.memory.put(request, suite)

    def count(self) -> int:
        return self.memory.count()


# Preserve the former import paths while keeping these definitions in one source file.
for _legacy_module in ("contracts", "registry", "roles", "storage_agent"):
    sys.modules[f"{__name__}.{_legacy_module}"] = sys.modules[__name__]


__all__ = [
    "AgentCapability",
    "AgentDescriptor",
    "AgentKind",
    "AgentRegistry",
    "FunctionalAgentDescriptor",
    "RequirementToTestCaseAgent",
    "TestStorageAgent",
    "TestDesignAgent",
]
