"""Coordinator for the functional test-design agents."""

import logging
from dataclasses import dataclass

from app.agent_runtime import AgentEvent, AgentRuntime
from app.agents.input_agent import InputAgent
from app.agents.storage_agent import TestStorageAgent
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.test_case_validator import TestCaseValidatorAgent, ValidationReport
from app.models import GenerateRequest, TestFormat, TestSuite
from app.services.document_ingestion import ExtractedDocument

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
        self.runtime = runtime

    async def run(self, request: GenerateRequest) -> PipelineResult:
        known = self.storage.find(request)
        if known is not None:
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
        if self.runtime is not None:
            outcome = await self.runtime.run(request)
            return PipelineResult(outcome.suite, outcome.validation, trace=tuple(outcome.trace))
        generated = await self.generator.generate(request)
        validation = self.validator.validate(request, generated)
        suite = self.storage.store(request, generated) if validation.passed else generated
        return PipelineResult(suite, validation)

    async def run_document(
        self,
        filename: str,
        content: bytes,
        additional_context: str = "",
        output_format: TestFormat = TestFormat.NORMAL,
    ) -> PipelineResult:
        document, request = self.input_agent.from_document(
            filename, content, additional_context, output_format
        )
        result = await self.run(request)
        return PipelineResult(result.suite, result.validation, document, result.trace)
