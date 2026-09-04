from fastapi import Depends

from app.agent_runtime import AgentRuntime
from app.agents import AgentRegistry, TestStorageAgent
from app.agents.output_agent import OutputAgent
from app.agents.reqnroll_step_definition_agent import ReqnRollStepDefinitionAgent
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.test_case_validator import TestCaseValidatorAgent
from app.config import Settings, get_settings
from app.generator import create_generator
from app.memory import OrganizationalMemory
from app.services import (
    MultiAgentTestPipeline,
    RequirementToTestCaseService,
    TestGenerationService,
)
from app.services.document_ingestion import DocumentIngestionService, InputAgent


def get_agent_registry(settings: Settings = Depends(get_settings)) -> AgentRegistry:
    """Compose the governed Copilot, OpenAI API, and Codex fallback runtime."""
    return AgentRegistry(create_generator(settings))


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
    input_agent = InputAgent(DocumentIngestionService(max_file_bytes=settings.max_upload_bytes))
    runtime = (
        AgentRuntime(settings, generator, validator, storage)
        if settings.model_directed_runtime_enabled
        else None
    )
    return MultiAgentTestPipeline(input_agent, generator, validator, storage, runtime)
