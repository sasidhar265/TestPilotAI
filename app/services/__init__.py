"""Application use-case services and the functional test-design pipeline."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.agent_runtime import AgentEvent, AgentRuntime
from app.agents import AgentRegistry, TestStorageAgent
from app.agents.lifecycle_agents import BusinessRulesAgent, KnowledgeAgent, TestDataAgent
from app.memory import OrganizationalMemory
from app.models import BusinessRule, ExpandRequest, GenerateRequest, TestFormat, TestSuite
from app.observability import publish_lifecycle_event
from app.services.document_ingestion import ExtractedDocument, InputAgent

if TYPE_CHECKING:
    from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
    from app.agents.test_case_validator import TestCaseValidatorAgent, ValidationReport

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    suite: TestSuite
    validation: ValidationReport
    document: ExtractedDocument | None = None
    trace: tuple[AgentEvent, ...] = ()


class MultiAgentTestPipeline:
    """Input -> storage lookup -> generation -> validation -> validated storage."""

    def __init__(
        self,
        input_agent: InputAgent,
        generator: TestCaseGeneratorAgent,
        validator: TestCaseValidatorAgent,
        storage: TestStorageAgent,
        runtime: AgentRuntime | None = None,
    ) -> None:
        self.input_agent = input_agent
        self.generator = generator
        self.validator = validator
        self.storage = storage
        self.business_rules = BusinessRulesAgent()
        self.knowledge = KnowledgeAgent(storage)
        self.test_data = TestDataAgent()
        self.runtime = runtime

    async def run(self, request: GenerateRequest) -> PipelineResult:
        request = self.business_rules.enrich(request)
        publish_lifecycle_event(
            "Business Rules Agent",
            "enrich_requirements",
            "success",
            f"Prepared {len(request.business_rules)} explicit business rules for orchestration.",
        )
        known = self.knowledge.recall(request)
        if known is not None:
            publish_lifecycle_event(
                "Knowledge Agent",
                "recall_approved_suite",
                "success",
                f"Reused an exact approved suite containing {len(known.test_cases)} cases.",
            )
            logger.info(
                "memory_lookup result=hit memory_key=%s copilot_contacted=false cases=%s",
                known.memory_key,
                len(known.test_cases),
            )
            validation = self.validator.validate(request, known)
            trace = (
                AgentEvent(
                    sequence=1,
                    tool="lookup_memory",
                    status="success",
                    summary=(
                        f"Found {len(known.test_cases)} reusable cases locally; "
                        "Copilot was not contacted."
                    ),
                ),
            )
            return PipelineResult(known, validation, trace=trace)
        logger.info("memory_lookup result=miss copilot_contacted=true")
        publish_lifecycle_event(
            "Knowledge Agent",
            "recall_approved_suite",
            "miss",
            "No exact approved suite matched; new governed generation is required.",
        )
        if self.runtime is not None:
            outcome = await self.runtime.run(request)
            return PipelineResult(outcome.suite, outcome.validation, trace=tuple(outcome.trace))
        generated = self.test_data.generate(await self.generator.generate(request))
        validation = self.validator.validate(request, generated)
        suite = self.knowledge.remember(request, generated) if validation.passed else generated
        return PipelineResult(suite, validation)

    async def run_document(
        self,
        filename: str,
        content: bytes,
        additional_context: str = "",
        output_format: TestFormat = TestFormat.NORMAL,
        business_rules: list[BusinessRule] | None = None,
    ) -> PipelineResult:
        document, request = self.input_agent.from_document(
            filename, content, additional_context, output_format
        )
        request = request.model_copy(update={"business_rules": business_rules or []})
        result = await self.run(request)
        return PipelineResult(result.suite, result.validation, document, result.trace)


class TestGenerationService:
    """Application boundary for test-design use cases."""

    def __init__(self, registry: AgentRegistry, memory: OrganizationalMemory) -> None:
        from app.agents.output_agent import OutputAgent
        from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
        from app.agents.test_case_validator import TestCaseValidatorAgent

        self.registry = registry
        self.memory = memory
        validator = TestCaseValidatorAgent()
        knowledge_source = OutputAgent(memory.path, memory.enabled)
        self.pipeline = MultiAgentTestPipeline(
            InputAgent(),
            TestCaseGeneratorAgent(registry, validator, knowledge_source),
            validator,
            TestStorageAgent(memory),
        )

    async def generate(self, request: GenerateRequest) -> TestSuite:
        return (await self.pipeline.run(request)).suite

    async def expand(self, expansion: ExpandRequest) -> TestSuite:
        return await self.registry.get_test_design_agent().generate(
            expansion.request,
            phase="expand",
            existing_titles=expansion.existing_titles,
        )


class RequirementToTestCaseService:
    """Orchestrate normalized requirement-to-test conversion."""

    def __init__(self, registry: AgentRegistry, memory: OrganizationalMemory) -> None:
        self.registry = registry
        self.memory = memory

    async def convert(self, request: GenerateRequest) -> TestSuite:
        known_suite = self.memory.get(request)
        if known_suite is not None:
            return known_suite
        agent = self.registry.get_requirement_to_test_case_agent()
        generated = await agent.generate(request)
        return self.memory.put(request, generated)

    async def expand(self, expansion: ExpandRequest) -> TestSuite:
        agent = self.registry.get_requirement_to_test_case_agent()
        return await agent.generate(
            expansion.request,
            phase="expand",
            existing_titles=expansion.existing_titles,
        )


# Preserve former import paths for callers while maintaining one service source file.
for _legacy_module in (
    "multi_agent_pipeline",
    "requirement_to_test_cases",
    "test_generation",
):
    sys.modules[f"{__name__}.{_legacy_module}"] = sys.modules[__name__]


__all__ = [
    "MultiAgentTestPipeline",
    "PipelineResult",
    "RequirementToTestCaseService",
    "TestGenerationService",
]
