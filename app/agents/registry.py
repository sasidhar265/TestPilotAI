from app.agents.contracts import (
    AgentCapability,
    RequirementToTestCaseAgent,
    TestDesignAgent,
)


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
