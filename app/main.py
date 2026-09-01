import hmac
import logging
import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.agent_runtime import AgentEvent
from app.agents import TestStorageAgent
from app.agents.context_converter_agent import ContextConversionError, ContextConverterAgent
from app.agents.lifecycle_agents import (
    BugReporterAgent,
    BusinessRulesAgent,
    ExecutionAgent,
    KnowledgeAgent,
    MetricsAgent,
    TestDataAgent,
)
from app.agents.output_agent import OutputAgent
from app.agents.reqnroll_step_definition_agent import (
    ReqnRollStepDefinitionAgent,
    StepDefinitionArtifact,
    StepDefinitionRequest,
)
from app.agents.runner import CopilotGenerationError
from app.agents.test_case_generator_agent import (
    AutomationTestCaseGeneratorAgent,
    ManualTestCaseGeneratorAgent,
    ManualTestingSpecialistAgent,
    SpecForgeTransformerAgent,
    TestCaseGeneratorAgent,
)
from app.agents.test_case_validator import TestCaseValidatorAgent, ValidationReport
from app.auth import SESSION_COOKIE, issue_browser_session, valid_session
from app.config import Settings, get_settings
from app.dependencies import (
    get_multi_agent_pipeline,
    get_reqnroll_step_definition_agent,
    get_test_generation_service,
)
from app.exporter import suite_to_csv
from app.generator import CopilotGenerator, copilot_error_message
from app.jira import JiraClient
from app.memory import OrganizationalMemory
from app.models import (
    AcceptanceReceipt,
    AcceptSuiteRequest,
    BusinessRule,
    DefectDraft,
    DocumentSource,
    ExecutionRequest,
    ExecutionSummary,
    ExpandRequest,
    ExportFormat,
    GenerateRequest,
    GenerationTarget,
    JiraPublishRequest,
    JiraPublishResult,
    ManualTestingType,
    MetricsReport,
    SuiteRequest,
    TestFormat,
    TestSuite,
)
from app.observability import (
    OrganizationHttpMiddleware,
    configure_logging,
    generation_cancellations,
    lifecycle_events,
    publish_lifecycle_event,
    request_id_context,
    ui_log_handler,
)
from app.services import MultiAgentTestPipeline, TestGenerationService
from app.services.accepted_outputs import AcceptanceError, AcceptedOutputService
from app.services.document_ingestion import DocumentIngestionError, InputAgent

settings_at_startup = get_settings()
configure_logging(settings_at_startup.log_level, settings_at_startup.json_logs)
app = FastAPI(
    title="Quality Lifecycle Studio API",
    version="0.1.0",
    description="Governed multi-agent conversion of product requirements into validated tests.",
    docs_url=None if settings_at_startup.is_production else "/docs",
    redoc_url=None if settings_at_startup.is_production else "/redoc",
    openapi_url=None if settings_at_startup.is_production else "/openapi.json",
)
app.add_middleware(
    OrganizationHttpMiddleware,
    settings=settings_at_startup,
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings_at_startup.allowed_host_list,
)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
INDEX = Path(__file__).parent / "static" / "index.html"
DOCUMENTATION = Path(__file__).parent / "static" / "documentation.html"
LOGS = Path(__file__).parent / "static" / "logs.html"
LOGIN = Path(__file__).parent / "static" / "login.html"
logger = logging.getLogger(__name__)
HTML_HEADERS = {"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"}


def parse_business_rule_lines(value: str) -> list[BusinessRule]:
    """Parse editable rule overlays while preserving explicit BR identifiers."""
    rules: list[BusinessRule] = []
    seen: set[str] = set()
    for index, raw_line in enumerate(value.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        candidate_id, separator, candidate_description = line.partition(":")
        if separator and candidate_id.strip().upper().startswith("BR-"):
            rule_id = candidate_id.strip().upper()
            description = candidate_description.strip()
        else:
            rule_id = f"BR-{index:03d}"
            description = line
        if rule_id in seen:
            raise DocumentIngestionError(f"Business rule {rule_id} is duplicated.")
        try:
            rule = BusinessRule(id=rule_id, description=description)
        except ValueError as error:
            raise DocumentIngestionError(
                f"Business rule line {index} must use BR-ID: description."
            ) from error
        rules.append(rule)
        seen.add(rule_id)
    if len(rules) > 100:
        raise DocumentIngestionError("A maximum of 100 business rules can be supplied.")
    return rules


def log_operation_failure(operation: str, status_code: int, error: Exception) -> None:
    """Record actionable failure context and a payload-free traceback for diagnostics."""
    logger.error(
        "operation_failed operation=%s status=%s error_type=%s",
        operation,
        status_code,
        type(error).__name__,
        exc_info=(type(error), error, error.__traceback__),
    )


def complete_lifecycle_action(agent: str, action: str, summary: str) -> None:
    publish_lifecycle_event(agent, action, "success", summary)
    lifecycle_events.complete(request_id_context.get())


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


class MetricsRequest(SuiteRequest):
    execution: ExecutionSummary | None = None
    defects: list[DefectDraft] = Field(default_factory=list)


class CompanyDocument(BaseModel):
    id: str
    title: str
    content: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


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


@app.get("/login", include_in_schema=False)
async def login_page(request: Request) -> Response:
    if valid_session(request.cookies.get(SESSION_COOKIE, ""), settings_at_startup):
        return RedirectResponse("/", status_code=303)
    return FileResponse(LOGIN, headers=HTML_HEADERS)


@app.post("/api/auth/login", include_in_schema=False)
async def login(credentials: LoginRequest) -> Response:
    if not settings_at_startup.browser_login_enabled:
        raise HTTPException(status_code=503, detail="Browser login is not configured")
    username_ok = hmac.compare_digest(credentials.username, settings_at_startup.app_username)
    password_ok = hmac.compare_digest(credentials.password, settings_at_startup.app_password_value)
    if not username_ok or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    response = Response(content='{"authenticated":true}', media_type="application/json")
    response.set_cookie(
        SESSION_COOKIE,
        issue_browser_session(credentials.username, settings_at_startup),
        max_age=settings_at_startup.session_ttl_seconds,
        httponly=True,
        secure=settings_at_startup.is_production,
        samesite="strict",
        path="/",
    )
    return response


@app.post("/api/auth/logout", include_in_schema=False)
async def logout() -> Response:
    response = Response(content='{"authenticated":false}', media_type="application/json")
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return response


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(INDEX, headers=HTML_HEADERS)


@app.get("/documentation", include_in_schema=False)
async def documentation() -> FileResponse:
    return FileResponse(DOCUMENTATION, headers=HTML_HEADERS)


@app.get("/logs", include_in_schema=False)
async def logs() -> FileResponse:
    return FileResponse(LOGS, headers=HTML_HEADERS)


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
        "agent_profile": settings.agent_profile,
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


@app.get("/api/live")
async def liveness() -> dict[str, bool]:
    """Report process liveness without touching providers or persistent storage."""
    return {"ok": True}


@app.get("/api/ready")
async def readiness(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Verify local dependencies needed to accept work; no premium AI request is consumed."""
    checks: dict[str, bool] = {
        "configuration": True,
        "agent_profile": True,
        "memory": True,
    }
    profile = (
        settings.copilot_working_directory / ".github" / "agent-profiles" / settings.agent_profile
    )
    checks["agent_profile"] = profile.is_dir()
    if settings.organizational_memory_enabled:
        memory_parent = settings.organizational_memory_path.parent
        try:
            memory_parent.mkdir(parents=True, exist_ok=True)
            checks["memory"] = os.access(memory_parent, os.W_OK)
            if checks["memory"]:
                OrganizationalMemory(settings.organizational_memory_path).count()
        except OSError:
            checks["memory"] = False
    ready = all(checks.values())
    if not ready:
        raise HTTPException(status_code=503, detail={"ready": False, "checks": checks})
    return {"ready": True, "checks": checks, "upstream_copilot_checked": False}


@app.get("/api/agents")
async def list_agents() -> list[dict[str, object]]:
    """List the functional agents in execution order."""
    return [
        agent.model_dump(mode="json")
        for agent in (
            InputAgent.descriptor,
            BusinessRulesAgent.descriptor,
            KnowledgeAgent.descriptor,
            TestCaseGeneratorAgent.descriptor,
            SpecForgeTransformerAgent.descriptor,
            ManualTestCaseGeneratorAgent.descriptor,
            ManualTestingSpecialistAgent.descriptor,
            AutomationTestCaseGeneratorAgent.descriptor,
            TestCaseValidatorAgent.descriptor,
            ContextConverterAgent.descriptor,
            OutputAgent.descriptor,
            TestStorageAgent.descriptor,
            TestDataAgent.descriptor,
            ExecutionAgent.descriptor,
            BugReporterAgent.descriptor,
            MetricsAgent.descriptor,
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


@app.get("/api/generation/{request_id}/events")
async def generation_events(request_id: str, after: int = 0) -> dict[str, object]:
    """Return incremental, payload-free lifecycle activity for one correlated generation."""
    if not request_id.isascii() or len(request_id) > 128 or after < 0:
        raise HTTPException(status_code=422, detail="Invalid lifecycle event query")
    return lifecycle_events.read(request_id, after)


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


@app.post("/api/test-data", response_model=TestSuite)
async def generate_test_data(request: SuiteRequest) -> TestSuite:
    """Fill missing case-aligned values with safe synthetic test data."""
    suite = TestDataAgent().generate(request.suite)
    complete_lifecycle_action(
        "Test Data Agent",
        "generate_synthetic_data",
        f"Prepared case-aligned synthetic data for {len(suite.test_cases)} cases.",
    )
    return suite


@app.post("/api/execution", response_model=ExecutionSummary)
async def summarize_execution(request: ExecutionRequest) -> ExecutionSummary:
    """Validate and summarize results supplied by an approved execution source."""
    try:
        summary = ExecutionAgent().summarize(request)
        complete_lifecycle_action(
            "Execution Agent",
            "summarize_execution",
            f"Summarized {summary.total} reviewed results with a {summary.pass_rate}% pass rate.",
        )
        return summary
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/defects", response_model=list[DefectDraft])
async def draft_defects(request: ExecutionRequest) -> list[DefectDraft]:
    """Create human-review-required defect drafts from failed test results."""
    try:
        ExecutionAgent().summarize(request)
        defects = BugReporterAgent().draft(request.suite, request.results)
        complete_lifecycle_action(
            "Bug Reporter Agent",
            "draft_defects",
            f"Created {len(defects)} review-required defect drafts from failed evidence.",
        )
        return defects
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/metrics", response_model=MetricsReport)
async def generate_metrics(request: MetricsRequest) -> MetricsReport:
    """Calculate transparent coverage, execution, and defect metrics."""
    report = MetricsAgent().calculate(request.suite, request.execution, request.defects)
    complete_lifecycle_action(
        "Metrics Agent",
        "calculate_metrics",
        f"Calculated metrics for {report.total_tests} tests and {report.total_defects} defects.",
    )
    return report


@app.post("/api/agent/run", response_model=AgentRunResult)
async def run_agent(
    request: GenerateRequest,
    pipeline: MultiAgentTestPipeline = Depends(get_multi_agent_pipeline),
) -> AgentRunResult:
    """Run the deterministic SpecForge coordinator and its governed specialists."""
    request_id = request_id_context.get()
    lifecycle_events.start(request_id)
    publish_lifecycle_event(
        "Input Agent",
        "normalize_text",
        "success",
        "Validated and normalized the UI requirement into the typed request envelope.",
    )
    generation_cancellations.register(request_id, "agent_test_case_generation")
    try:
        result = await pipeline.run(request)
        return AgentRunResult(
            suite=result.suite,
            validation=result.validation,
            trace=list(getattr(result, "trace", ())),
        )
    except CopilotGenerationError as error:
        publish_lifecycle_event(
            "QA Master Agent",
            "coordinate",
            "failed",
            "Coordinator stopped safely before completing the governed lifecycle.",
        )
        log_operation_failure("agent_run", 503, error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        log_operation_failure("agent_run", 502, error)
        raise HTTPException(status_code=502, detail=copilot_error_message(error)) from error
    finally:
        generation_cancellations.unregister(request_id)
        lifecycle_events.complete(request_id)


@app.post("/api/generate/document", response_model=DocumentGenerationResult)
async def generate_from_document(
    file: UploadFile = File(...),
    output_format: TestFormat = Form(TestFormat.NORMAL),
    generation_target: GenerationTarget = Form(GenerationTarget.AUTO),
    manual_testing_type: ManualTestingType = Form(ManualTestingType.API),
    additional_context: str = Form(""),
    business_rules: str = Form(""),
    pipeline: MultiAgentTestPipeline = Depends(get_multi_agent_pipeline),
) -> DocumentGenerationResult:
    """Extract requirements, generate test cases, then independently validate them."""
    filename = file.filename or "uploaded-document"
    request_id = request_id_context.get()
    lifecycle_events.start(request_id)
    publish_lifecycle_event(
        "Input Agent",
        "ingest_document",
        "running",
        "Reading the supported document within configured safety limits.",
    )
    generation_cancellations.register(request_id, "document_test_case_generation")
    try:
        if file.size is not None and file.size > settings_at_startup.max_upload_bytes:
            raise DocumentIngestionError(
                "The uploaded document exceeds the "
                f"{settings_at_startup.max_upload_bytes}-byte limit."
            )
        rules = parse_business_rule_lines(business_rules)
        result = await pipeline.run_document(
            filename,
            await file.read(),
            additional_context,
            output_format,
            rules,
            manual_testing_type,
            generation_target,
        )
        document = result.document
        assert document is not None
        publish_lifecycle_event(
            "Input Agent",
            "ingest_document",
            "success",
            f"Extracted {len(document.text)} normalized characters for the request envelope.",
        )
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
        lifecycle_events.complete(request_id)


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
        complete_lifecycle_action(
            "Context Converter → Output Agent",
            "convert_and_store",
            f"Produced and retained the approved {output_format.value} artifact.",
        )
    except ContextConversionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        artifact.content,
        media_type=artifact.media_type,
        headers={"Content-Disposition": f'attachment; filename="{artifact.filename}"'},
    )


@app.post("/api/output/accept", response_model=AcceptanceReceipt)
async def accept_selected_tests(
    request: AcceptSuiteRequest,
    settings: Settings = Depends(get_settings),
) -> AcceptanceReceipt:
    """Persist explicitly selected, quality-gate-approved manual and automation artifacts."""
    try:
        receipt = AcceptedOutputService(settings.accepted_output_directory).accept(request)
        complete_lifecycle_action(
            "Output Agent",
            "accept_selected_tests",
            (
                f"Accepted {len(receipt.selected_case_ids)} cases into "
                f"{len(receipt.artifacts)} artifacts."
            ),
        )
        return receipt
    except AcceptanceError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/step-definitions/reqnroll", response_model=StepDefinitionArtifact)
async def generate_reqnroll_step_definitions(
    request: StepDefinitionRequest,
    agent: ReqnRollStepDefinitionAgent = Depends(get_reqnroll_step_definition_agent),
) -> StepDefinitionArtifact:
    """Generate reviewable C# bindings from Quality Gate-approved automation scenarios."""
    try:
        artifact = await agent.generate(request)
        complete_lifecycle_action(
            "ReqnRoll Agent",
            "generate_step_definitions",
            (
                f"Generated {len(artifact.files)} C# files with "
                f"{len(artifact.coverage)} step mappings."
            ),
        )
        return artifact
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CopilotGenerationError as error:
        log_operation_failure("generate_reqnroll_step_definitions", 503, error)
        raise HTTPException(status_code=503, detail=str(error)) from error


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
        result = await JiraClient(settings).publish(
            request.issue_key.upper(), selected_suite, request.add_comment
        )
        complete_lifecycle_action(
            "Jira Publishing Agent",
            "publish_selected_cases",
            f"Published {len(selected_cases)} explicitly selected cases to {result.issue_key}.",
        )
        return result
    except HTTPException:
        raise
    except RuntimeError as error:
        log_operation_failure("jira_publish", 503, error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        log_operation_failure("jira_publish", 502, error)
        raise HTTPException(status_code=502, detail="Jira publish failed") from error
