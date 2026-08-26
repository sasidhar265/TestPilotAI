"""Coordinator for the functional test-design agents."""

from dataclasses import dataclass

from app.agents.input_agent import InputAgent
from app.agents.storage_agent import TestStorageAgent
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.test_case_validator import TestCaseValidatorAgent, ValidationReport
from app.models import GenerateRequest, TestFormat, TestSuite
from app.services.document_ingestion import ExtractedDocument


@dataclass(frozen=True)
class PipelineResult:
    suite: TestSuite
    validation: ValidationReport
    document: ExtractedDocument | None = None


class MultiAgentTestPipeline:
    """Input -> storage lookup -> generation -> validation -> validated storage."""

    def __init__(
        self,
        input_agent: InputAgent,
        generator: TestCaseGeneratorAgent,
        validator: TestCaseValidatorAgent,
        storage: TestStorageAgent,
    ) -> None:
        self.input_agent = input_agent
        self.generator = generator
        self.validator = validator
        self.storage = storage

    async def run(self, request: GenerateRequest) -> PipelineResult:
        known = self.storage.find(request)
        if known is not None:
            return PipelineResult(known, self.validator.validate(request, known))
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
        return PipelineResult(result.suite, result.validation, document)
