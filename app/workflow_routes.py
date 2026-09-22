"""Five-stage requirement workflow; execution stays within the configured project."""

import asyncio
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.agents.context_converter_agent import ContextConverterAgent
from app.agents.requirements_validation import RequirementsReport, RequirementsValidationAgent
from app.agents.runner import CopilotGenerationError
from app.agents.test_case_validator import TestCaseValidatorAgent
from app.agents.workflow_agent import WorkflowAgent, test_case_request
from app.config import Settings, get_settings
from app.dependencies import get_multi_agent_pipeline
from app.jira import JiraClient
from app.models import AutomationRunRequest, GenerateRequest, SuiteRequest
from app.observability import (
    generation_cancellations,
    lifecycle_events,
    publish_lifecycle_event,
    request_id_context,
)
from app.pdf_exporter import brd_draft_to_pdf
from app.services import MultiAgentTestPipeline
from app.services.document_ingestion import DocumentIngestionError, DocumentIngestionService
from app.uploaded_brd import issue_brd_receipt
from app.workflow_models import (
    JiraStoriesRequest,
    ScenarioHandoff,
    Scenarios,
    Stories,
    StoryHandoff,
)

router = APIRouter(prefix="/api/workflow", tags=["Five-stage workflow"])


class ExecutionPlanRequest(SuiteRequest):
    request: GenerateRequest


Config = Annotated[Settings, Depends(get_settings)]
Pipeline = Annotated[MultiAgentTestPipeline, Depends(get_multi_agent_pipeline)]


@contextmanager
def stage_operation(label: str, *, complete: bool = True) -> Iterator[None]:
    """Expose live progress and cancellation for a workflow operation."""
    request_id = request_id_context.get()
    lifecycle_events.start(request_id)
    generation_cancellations.register(request_id, label)
    publish_lifecycle_event(label, "workflow_stage", "running", f"{label} started.")
    succeeded = False
    try:
        yield
        succeeded = True
        publish_lifecycle_event(label, "workflow_stage", "success", f"{label} finished.")
    except asyncio.CancelledError as error:
        publish_lifecycle_event(label, "workflow_stage", "failed", f"{label} cancelled.")
        raise HTTPException(499, f"{label} cancelled.") from error
    except Exception:
        publish_lifecycle_event(
            label, "workflow_stage", "failed", f"{label} failed. Review the operation status."
        )
        raise
    finally:
        generation_cancellations.unregister(request_id)
        if complete or not succeeded:
            lifecycle_events.complete(request_id)


@router.post("/requirements/document")
async def read_document(file: UploadFile, settings: Config) -> dict[str, str]:
    with stage_operation("Requirements processing", complete=False):
        content = await file.read(settings.max_upload_bytes + 1)
        try:
            document = await asyncio.to_thread(
                DocumentIngestionService(max_file_bytes=settings.max_upload_bytes).extract,
                file.filename or "document",
                content,
            )
        except DocumentIngestionError as error:
            raise HTTPException(422, str(error)) from error
        return {"description": document.text, "filename": document.filename,
                "uploaded_brd_receipt": issue_brd_receipt(document.text, settings)}


@router.post("/validate-requirements", response_model=RequirementsReport)
async def validate_requirements(request: GenerateRequest, settings: Config) -> RequirementsReport:
    with stage_operation("Requirements validation"):
        return await RequirementsValidationAgent(settings).require(request)


@router.post("/brd/pdf")
async def download_brd_draft(text: Annotated[str, Form(min_length=1, max_length=50000)]) -> Response:
    return Response(
        content=brd_draft_to_pdf(text),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="proposed-brd.pdf"'},
    )


@router.post("/stories", response_model=Stories)
async def create_stories(request: GenerateRequest, settings: Config) -> Stories:
    request_id = request_id_context.get()
    lifecycle_events.start(request_id)
    generation_cancellations.register(request_id, "story_generation")
    publish_lifecycle_event(
        "Story Agent", "create_stories", "running", "Creating stories from source requirements."
    )
    try:
        stories = await WorkflowAgent(settings).stories(request)
        publish_lifecycle_event(
            "Story Agent",
            "create_stories",
            "success",
            "Stories validated against source requirements and ready for review.",
        )
        return stories
    except asyncio.CancelledError as error:
        publish_lifecycle_event(
            "Story Agent", "create_stories", "failed", "Story generation cancelled by the user."
        )
        raise HTTPException(499, "Story generation cancelled.") from error
    except CopilotGenerationError as error:
        publish_lifecycle_event(
            "Story Agent",
            "create_stories",
            "failed",
            "Story generation failed. Retry from the requirements form.",
        )
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        publish_lifecycle_event(
            "Story Agent",
            "create_stories",
            "failed",
            "Story validation failed. Review the requirements and retry.",
        )
        raise HTTPException(422, str(error)) from error
    finally:
        generation_cancellations.unregister(request_id)
        lifecycle_events.complete(request_id)


@router.post("/scenarios", response_model=Scenarios)
async def create_scenarios(request: StoryHandoff, settings: Config) -> Scenarios:
    with stage_operation("Scenario generation"):
        try:
            return await WorkflowAgent(settings).scenarios(request)
        except CopilotGenerationError as error:
            raise HTTPException(503, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error


@router.post("/test-cases")
async def create_cases(request: ScenarioHandoff, pipeline: Pipeline) -> dict[str, Any]:
    with stage_operation("Test case generation"):
        try:
            source = test_case_request(request)
            result = await pipeline.run(source)
            covered = {
                ref for case in result.suite.test_cases for ref in case.acceptance_criteria_covered
            }
            required = {scenario.id for scenario in request.scenarios.scenarios}
            required.update(story.id for story in request.stories.stories)
            if not required <= covered:
                raise ValueError(
                    "Generated cases did not cover all story/scenario IDs. Retry generation."
                )
        except ValidationError as error:
            raise HTTPException(
                422,
                "The reviewed stage handoff contains invalid fields. Review stories and "
                "scenarios, then try again.",
            ) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        except CopilotGenerationError as error:
            raise HTTPException(503, str(error)) from error
        return {"suite": result.suite, "validation": result.validation, "source_request": source}


def execution_plan(request: ExecutionPlanRequest, settings: Settings) -> dict[str, Any]:
    project = Path(settings.automation_project_path).resolve()
    root = Path.cwd().resolve()
    if root not in project.parents or not project.is_file() or project.suffix != ".csproj":
        return {
            "ready": False,
            "cases": [],
            "reason": "Configure an approved ReqnRoll project first.",
        }
    validation = TestCaseValidatorAgent().validate(request.request, request.suite)
    try:
        expected = ContextConverterAgent()._feature(request.suite).decode().strip()
    except ValueError as error:
        return {"ready": False, "cases": [], "reason": str(error)}
    generated_cases = [
        {
            "feature_file": "Features/generated.feature",
            "feature": request.suite.feature_name,
            "scenario": match.group(1),
            "status": "not-run",
        }
        for match in re.finditer(r"^\s*Scenario(?: Outline)?:\s*(.+)$", expected, re.MULTILINE)
    ]
    cases = []
    matched = False
    for path in sorted((project.parent / "Features").rglob("*.feature")):
        if project.parent not in path.resolve().parents or path.stat().st_size > 1_000_000:
            continue
        content = path.read_text(encoding="utf-8-sig")
        matched = matched or content.strip() == expected
        feature = re.search(r"^\s*Feature:\s*(.+)$", content, re.MULTILINE)
        for match in re.finditer(r"^\s*Scenario(?: Outline)?:\s*(.+)$", content, re.MULTILINE):
            cases.append(
                {
                    "feature_file": str(path.relative_to(project.parent)),
                    "feature": feature.group(1) if feature else path.stem,
                    "scenario": match.group(1),
                    "status": "not-run",
                }
            )
    ready = matched and validation.passed and bool(cases)
    return {
        "ready": ready,
        "cases": cases if ready else generated_cases,
        "project": str(project.relative_to(root)),
        "reason": "Run all features in this configured project; outlines expand into example cases."
        if ready
        else "Generate and install the approved automation pack in the configured ReqnRoll "
        "project, including bindings and input data. Its feature must match this suite exactly "
        "and the suite must pass the Quality Gate.",
    }


@router.post("/execution-plan")
async def get_execution_plan(request: ExecutionPlanRequest, settings: Config) -> dict[str, Any]:
    with stage_operation("Execution planning"):
        await RequirementsValidationAgent(settings).require(request.request)
        return execution_plan(request, settings)


@router.post("/execute")
async def execute(request: ExecutionPlanRequest, settings: Config) -> Any:
    with stage_operation("Test execution"):
        await RequirementsValidationAgent(settings).require(request.request)
        plan = execution_plan(request, settings)
        if not plan["ready"]:
            raise HTTPException(422, plan["reason"])
        from app.main import _automation_run_lock, _run_automation

        if _automation_run_lock.locked():
            raise HTTPException(409, "A BDD run is already in progress")
        async with _automation_run_lock:
            return await _run_automation(
                AutomationRunRequest(), settings, scope="configured-feature-project"
            )


@router.post("/validate-stories")
async def validate_stories(request: StoryHandoff) -> StoryHandoff:
    return request


@router.post("/jira-stories")
async def publish_stories(request: JiraStoriesRequest, settings: Config) -> dict[str, Any]:
    try:
        return {"results": await JiraClient(settings).create_stories(request)}
    except RuntimeError as error:
        raise HTTPException(503, str(error)) from error


@router.post("/validate-scenarios")
async def validate_scenarios(request: ScenarioHandoff) -> ScenarioHandoff:
    return request
