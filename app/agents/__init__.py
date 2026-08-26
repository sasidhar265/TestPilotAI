"""Agent runtime contracts and registration policy."""

from app.agents.contracts import (
    AgentCapability,
    AgentDescriptor,
    RequirementToTestCaseAgent,
    TestDesignAgent,
)
from app.agents.input_agent import InputAgent
from app.agents.registry import AgentRegistry
from app.agents.storage_agent import TestStorageAgent
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.test_case_validator import TestCaseValidatorAgent

__all__ = [
    "AgentCapability",
    "AgentDescriptor",
    "AgentRegistry",
    "RequirementToTestCaseAgent",
    "TestDesignAgent",
    "InputAgent",
    "TestCaseGeneratorAgent",
    "TestCaseValidatorAgent",
    "TestStorageAgent",
]
