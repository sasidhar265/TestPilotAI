from fastapi import Depends

from app.agents import AgentRegistry, TestStorageAgent
from app.agents.output_agent import OutputAgent
from app.agents.reqnroll_step_definition_agent import ReqnRollStepDefinitionAgent
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.test_case_validator import TestCaseValidatorAgent
from app.config import Settings, get_settings
from app.generator import CopilotGenerator
from app.memory import OrganizationalMemory
from app.services import (
    MultiAgentTestPipeline,
    RequirementToTestCaseService,
    TestGenerationService,
)
from app.services.document_ingestion import InputAgent


def get_agent_registry(settings: Settings = Depends(get_settings)) -> AgentRegistry:
    """Composition root: GitHub Copilot is intentionally the only registered runtime."""
    return AgentRegistry(CopilotGenerator(settings))


def get_reqnroll_step_definition_agent(
    settings: Settings = Depends(get_settings),
) -> ReqnRollStepDefinitionAgent:
    return ReqnRollStepDefinitionAgent(settings)


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
    validator = TestCaseValidatorAgent()
    knowledge_source = OutputAgent(
        settings.organizational_memory_path,
        enabled=settings.organizational_memory_enabled,
    )
    generator = TestCaseGeneratorAgent(registry, validator, knowledge_source)
    storage = TestStorageAgent(memory)
    return MultiAgentTestPipeline(InputAgent(), generator, validator, storage)
