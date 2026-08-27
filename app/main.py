import logging
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent_runtime import AgentEvent
from app.agents.context_converter_agent import ContextConversionError, ContextConverterAgent
from app.agents.input_agent import InputAgent
from app.agents.output_agent import OutputAgent
from app.agents.specialist_agents import (
    AutomationTestCaseGeneratorAgent,
    ManualTestCaseGeneratorAgent,
)
from app.agents.storage_agent import TestStorageAgent
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.test_case_validator import TestCaseValidatorAgent, ValidationReport
from app.cancellation import generation_cancellations
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
    ExportFormat,
    GenerateRequest,
    JiraPublishRequest,
    JiraPublishResult,
    TestFormat,
    TestSuite,
)
from app.observability import configure_logging, request_id_context, ui_log_handler
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
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
INDEX = Path(__file__).parent / "static" / "index.html"
DOCUMENTATION = Path(__file__).parent / "static" / "documentation.html"
LOGS = Path(__file__).parent / "static" / "logs.html"
logger = logging.getLogger(__name__)


def log_operation_failure(operation: str, status_code: int, error: Exception) -> None:
    """Record actionable failure context and a payload-free traceback for diagnostics."""
    logger.error(
        "operation_failed operation=%s status=%s error_type=%s",
        operation,
        status_code,
        type(error).__name__,
        exc_info=(type(error), error, error.__traceback__),
    )


class DocumentGenerationResult(DocumentSource):
    suite: TestSuite
    validation: ValidationReport
    trace: list[AgentEvent] = Field(default_factory=list)


class AgentRunResult(BaseModel):
    suite: TestSuite
    validation: ValidationReport
    trace: list[AgentEvent]


class ContextConversionRequest(BaseModel):
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


@app.get("/logs", include_in_schema=False)
async def logs() -> FileResponse:
    return FileResponse(LOGS)


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
    output_agent = OutputAgent(
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
        "approved_output_entries": output_agent.count(),
        "approved_scenario_entries": output_agent.scenario_count(),
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
            ManualTestCaseGeneratorAgent.descriptor,
            AutomationTestCaseGeneratorAgent.descriptor,
            TestCaseValidatorAgent.descriptor,
            ContextConverterAgent.descriptor,
            OutputAgent.descriptor,
            TestStorageAgent.descriptor,
        )
    ]


@app.get("/api/logs")
async def application_logs(request_id: str = "", limit: int = 100) -> dict[str, object]:
    """Return bounded operational logs, optionally filtered by an exact correlation ID."""
    if request_id and not request_id.isascii():
        raise HTTPException(status_code=422, detail="Reference ID must contain ASCII characters")
    safe_limit = max(1, min(limit, 200))
    entries = ui_log_handler.search(request_id=request_id.strip(), limit=safe_limit)
    return {"entries": entries, "count": len(entries)}


@app.post("/api/generate", response_model=TestSuite)
async def generate(
    request: GenerateRequest,
    service: TestGenerationService = Depends(get_test_generation_service),
) -> TestSuite:
    try:
        return await service.generate(request)
    except CopilotGenerationError as error:
        log_operation_failure("generate", 503, error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        log_operation_failure("generate", 502, error)
        raise HTTPException(status_code=502, detail=copilot_error_message(error)) from error


@app.post("/api/agent/run", response_model=AgentRunResult)
async def run_agent(
    request: GenerateRequest,
    pipeline: MultiAgentTestPipeline = Depends(get_multi_agent_pipeline),
) -> AgentRunResult:
    """Run the deterministic SpecForge coordinator and its governed specialists."""
    request_id = request_id_context.get()
    generation_cancellations.register(request_id, "agent_test_case_generation")
    try:
        result = await pipeline.run(request)
        return AgentRunResult(
            suite=result.suite,
            validation=result.validation,
            trace=list(getattr(result, "trace", ())),
        )
    except CopilotGenerationError as error:
        log_operation_failure("agent_run", 503, error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        log_operation_failure("agent_run", 502, error)
        raise HTTPException(status_code=502, detail=copilot_error_message(error)) from error
    finally:
        generation_cancellations.unregister(request_id)


@app.post("/api/generate/document", response_model=DocumentGenerationResult)
async def generate_from_document(
    file: UploadFile = File(...),
    output_format: TestFormat = Form(TestFormat.NORMAL),
    additional_context: str = Form(""),
    pipeline: MultiAgentTestPipeline = Depends(get_multi_agent_pipeline),
) -> DocumentGenerationResult:
    """Extract requirements, generate test cases, then independently validate them."""
    filename = file.filename or "uploaded-document"
    request_id = request_id_context.get()
    generation_cancellations.register(request_id, "document_test_case_generation")
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
            trace=list(getattr(result, "trace", ())),
        )
    except DocumentIngestionError as error:
        log_operation_failure("document_generation", 422, error)
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CopilotGenerationError as error:
        log_operation_failure("document_generation", 503, error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        log_operation_failure("document_generation", 502, error)
        raise HTTPException(status_code=502, detail=copilot_error_message(error)) from error
    finally:
        generation_cancellations.unregister(request_id)


@app.post("/api/generation/{request_id}/cancel")
async def cancel_generation(request_id: str) -> dict[str, bool | str]:
    cancelled = generation_cancellations.cancel(request_id)
    return {"request_id": request_id, "cancelled": cancelled}


@app.post("/api/generate/expand", response_model=TestSuite)
async def expand_generation(
    expansion: ExpandRequest,
    service: TestGenerationService = Depends(get_test_generation_service),
) -> TestSuite:
    try:
        return await service.expand(expansion)
    except CopilotGenerationError as error:
        log_operation_failure("expand_generation", 503, error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        log_operation_failure("expand_generation", 502, error)
        raise HTTPException(status_code=502, detail=copilot_error_message(error)) from error


@app.post("/api/export/csv")
async def export_csv(suite: TestSuite) -> Response:
    return Response(
        suite_to_csv(suite),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="test-cases.csv"'},
    )


@app.post("/api/context-converter/{output_format}")
async def convert_validated_context(
    output_format: ExportFormat,
    request: ContextConversionRequest,
    settings: Settings = Depends(get_settings),
) -> Response:
    """Convert only quality-gate-approved output into Xray/Jira interchange files."""
    try:
        artifact = ContextConverterAgent().convert(request.suite, request.validation, output_format)
        OutputAgent(
            settings.organizational_memory_path,
            enabled=settings.organizational_memory_enabled,
        ).store(request.suite, output_format, artifact)
    except ContextConversionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
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
        log_operation_failure("jira_publish", 503, error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        log_operation_failure("jira_publish", 502, error)
        raise HTTPException(status_code=502, detail="Jira publish failed") from error
