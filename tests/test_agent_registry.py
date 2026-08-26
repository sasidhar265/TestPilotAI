import pytest

from app.agents import AgentCapability, AgentDescriptor, AgentRegistry
from app.config import Settings
from app.generator import CopilotGenerator


def test_registry_accepts_github_copilot() -> None:
    registry = AgentRegistry(CopilotGenerator(Settings()))

    assert registry.runtime_id == "github-copilot"
    assert AgentCapability.SPECFLOW_BDD in (
        registry.get_test_design_agent().descriptor.capabilities
    )


def test_registry_rejects_unapproved_runtime() -> None:
    class UnapprovedAgent:
        descriptor = AgentDescriptor(
            runtime_id="another-agent",
            display_name="Another agent",
            capabilities=frozenset({AgentCapability.TEST_DESIGN}),
        )

    with pytest.raises(ValueError, match="only 'github-copilot' is allowed"):
        AgentRegistry(UnapprovedAgent())
