from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.agents.input_agent import InputAgent
from app.agents.storage_agent import TestStorageAgent
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.test_case_validator import TestCaseValidatorAgent, ValidationReport
from app.config import Settings, get_settings
from app.dependencies import get_multi_agent_pipeline, get_test_generation_service
from app.errors import copilot_error_message
from app.exporter import suite_to_csv
from app.generator import CopilotGenerationError, CopilotGenerator
from app.jira import JiraClient
from app.memory import OrganizationalMemory
from app.middleware import OrganizationHttpMiddleware
from app.models import (
    DocumentSource,
    ExpandRequest,
    GenerateRequest,
    JiraPublishRequest,
    JiraPublishResult,
    TestFormat,
    TestSuite,
)
from app.observability import configure_logging
from app.services.document_ingestion import DocumentIngestionError
from app.services.multi_agent_pipeline import MultiAgentTestPipeline
from app.services.test_generation import TestGenerationService

settings_at_startup = get_settings()
configure_logging(settings_at_startup.log_level, settings_at_startup.json_logs)
app = FastAPI(
    title="Story-to-Tests Agent",
    version="0.1.0",
    description="Governed multi-agent conversion of product requirements into validated tests.",
)
app.add_middleware(OrganizationHttpMiddleware)
INDEX = Path(__file__).parent / "static" / "index.html"
DOCUMENTATION = Path(__file__).parent / "static" / "documentation.html"


class DocumentGenerationResult(DocumentSource):
    suite: TestSuite
    validation: ValidationReport


class CompanyDocument(BaseModel):
    id: str
    title: str
    content: str


COMPANY_DOCUMENTS = {
    "prerequisites": (
        "Company project prerequisites",
        Path(__file__).parent.parent / "docs" / "company-project-prerequisites.md",
    ),
    "requirements": (
        "Company solution requirements",
        Path(__file__).parent.parent / "docs" / "company-solution-requirements.md",
    ),
    "checklist": (
        "Company implementation checklist",
        Path(__file__).parent.parent / "docs" / "company-implementation-checklist.md",
    ),
}


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(INDEX)


@app.get("/documentation", include_in_schema=False)
async def documentation() -> FileResponse:
    return FileResponse(DOCUMENTATION)


@app.get("/api/documentation/company/{document_id}", response_model=CompanyDocument)
async def company_document(document_id: str) -> CompanyDocument:
    document = COMPANY_DOCUMENTS.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Unknown company document")
    title, path = document
    return CompanyDocument(id=document_id, title=title, content=path.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, bool | str | int]:
    memory = OrganizationalMemory(
        settings.organizational_memory_path,
        enabled=settings.organizational_memory_enabled,
    )
    return {
        "ok": True,
        "execution_host": "local-fastapi-uvicorn",
        "ai_provider": "github-copilot",
        "active_agent": CopilotGenerator.descriptor.display_name,
        "agent_runtime_id": CopilotGenerator.descriptor.runtime_id,
        "copilot_model": settings.copilot_model or "organization-default",
        "copilot_auth": "token" if settings.copilot_github_token else "signed-in-user",
        "organizational_memory": "enabled"
        if settings.organizational_memory_enabled
        else "disabled",
        "organizational_memory_entries": memory.count(),
        "jira_configured": all(
            [settings.jira_base_url, settings.jira_email, settings.jira_api_token]
        ),
    }


@app.get("/api/agents")
async def list_agents() -> list[dict[str, object]]:
    """List the functional agents in execution order."""
    return [
        agent.model_dump(mode="json")
        for agent in (
            InputAgent.descriptor,
            TestCaseGeneratorAgent.descriptor,
            TestCaseValidatorAgent.descriptor,
            TestStorageAgent.descriptor,
        )
    ]


@app.post("/api/generate", response_model=TestSuite)
async def generate(
    request: GenerateRequest,
    service: TestGenerationService = Depends(get_test_generation_service),
) -> TestSuite:
    try:
        return await service.generate(request)
    except CopilotGenerationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=copilot_error_message(error)) from error


@app.post("/api/generate/document", response_model=DocumentGenerationResult)
async def generate_from_document(
    file: UploadFile = File(...),
    output_format: TestFormat = Form(TestFormat.NORMAL),
    additional_context: str = Form(""),
    pipeline: MultiAgentTestPipeline = Depends(get_multi_agent_pipeline),
) -> DocumentGenerationResult:
    """Extract requirements, generate test cases, then independently validate them."""
    filename = file.filename or "uploaded-document"
    try:
        result = await pipeline.run_document(
            filename, await file.read(), additional_context, output_format
        )
        document = result.document
        assert document is not None
        return DocumentGenerationResult(
            filename=document.filename,
            media_type=document.media_type,
            extracted_characters=len(document.text),
            suite=result.suite,
            validation=result.validation,
        )
    except DocumentIngestionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CopilotGenerationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=copilot_error_message(error)) from error


@app.post("/api/generate/expand", response_model=TestSuite)
async def expand_generation(
    expansion: ExpandRequest,
    service: TestGenerationService = Depends(get_test_generation_service),
) -> TestSuite:
    try:
        return await service.expand(expansion)
    except CopilotGenerationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=copilot_error_message(error)) from error


@app.post("/api/export/csv")
async def export_csv(suite: TestSuite) -> Response:
    return Response(
        suite_to_csv(suite),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="test-cases.csv"'},
    )


@app.post("/api/jira/publish", response_model=JiraPublishResult)
async def publish_to_jira(
    request: JiraPublishRequest, settings: Settings = Depends(get_settings)
) -> JiraPublishResult:
    try:
        selected_ids = set(request.selected_case_ids)
        selected_cases = [case for case in request.suite.test_cases if case.id in selected_ids]
        missing_ids = selected_ids - {case.id for case in selected_cases}
        if missing_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown selected test case IDs: {', '.join(sorted(missing_ids))}",
            )
        selected_suite = request.suite.model_copy(update={"test_cases": selected_cases})
        return await JiraClient(settings).publish(
            request.issue_key.upper(), selected_suite, request.add_comment
        )
    except HTTPException:
        raise
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail="Jira publish failed") from error
