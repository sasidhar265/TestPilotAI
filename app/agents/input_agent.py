"""Input agent for text and document-based requirements."""

from app.agents.roles import AgentKind, FunctionalAgentDescriptor
from app.models import GenerateRequest, TestFormat
from app.services.document_ingestion import DocumentIngestionService, ExtractedDocument


class InputAgent:
    descriptor = FunctionalAgentDescriptor(
        id="input-agent",
        name="Input Agent",
        kind=AgentKind.INPUT,
        purpose="Normalize pasted requirements and extract requirements from supported documents.",
        runtime="local-deterministic",
        capabilities=("text", "docx", "pdf", "xlsx", "pages", "numbers", "png-ocr", "jpeg-ocr"),
    )

    def __init__(self, documents: DocumentIngestionService | None = None) -> None:
        self.documents = documents or DocumentIngestionService()

    def from_text(
        self,
        description: str,
        additional_context: str = "",
        output_format: TestFormat = TestFormat.NORMAL,
    ) -> GenerateRequest:
        return GenerateRequest(
            description=description,
            additional_context=additional_context,
            output_format=output_format,
        )

    def from_document(
        self,
        filename: str,
        content: bytes,
        additional_context: str = "",
        output_format: TestFormat = TestFormat.NORMAL,
    ) -> tuple[ExtractedDocument, GenerateRequest]:
        document = self.documents.extract(filename, content)
        return document, self.from_text(document.text, additional_context, output_format)
