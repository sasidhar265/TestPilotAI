from fastapi import Depends

from app.agent_runtime import AgentRuntime
from app.agents import AgentRegistry
from app.agents.input_agent import InputAgent
from app.agents.storage_agent import TestStorageAgent
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.test_case_validator import TestCaseValidatorAgent
from app.config import Settings, get_settings
from app.generator import CopilotGenerator
from app.memory import OrganizationalMemory
from app.services.multi_agent_pipeline import MultiAgentTestPipeline
from app.services.requirement_to_test_cases import RequirementToTestCaseService
from app.services.test_generation import TestGenerationService


def get_agent_registry(settings: Settings = Depends(get_settings)) -> AgentRegistry:
    """Composition root: GitHub Copilot is intentionally the only registered runtime."""
    return AgentRegistry(CopilotGenerator(settings))


def get_test_generation_service(
    registry: AgentRegistry = Depends(get_agent_registry),
    settings: Settings = Depends(get_settings),
) -> TestGenerationService:
    memory = OrganizationalMemory(
        settings.organizational_memory_path,
        enabled=settings.organizational_memory_enabled,
    )
    return TestGenerationService(registry, memory)


def get_requirement_to_test_case_service(
    registry: AgentRegistry = Depends(get_agent_registry),
    settings: Settings = Depends(get_settings),
) -> RequirementToTestCaseService:
    memory = OrganizationalMemory(
        settings.organizational_memory_path,
        enabled=settings.organizational_memory_enabled,
    )
    return RequirementToTestCaseService(registry, memory)


def get_multi_agent_pipeline(
    registry: AgentRegistry = Depends(get_agent_registry),
    settings: Settings = Depends(get_settings),
) -> MultiAgentTestPipeline:
    memory = OrganizationalMemory(
        settings.organizational_memory_path,
        enabled=settings.organizational_memory_enabled,
    )
    generator = TestCaseGeneratorAgent(registry)
    validator = TestCaseValidatorAgent()
    storage = TestStorageAgent(memory)
    runtime = AgentRuntime(settings, generator, validator, storage)
    return MultiAgentTestPipeline(InputAgent(), generator, validator, storage, runtime)
