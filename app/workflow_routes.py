"""Five-stage requirement workflow; execution stays within the configured project."""

import asyncio
import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import ValidationError

from app.agents.context_converter_agent import ContextConverterAgent
from app.agents.runner import CopilotGenerationError
from app.agents.test_case_validator import TestCaseValidatorAgent
from app.agents.workflow_agent import WorkflowAgent, test_case_request
from app.config import Settings, get_settings
from app.dependencies import get_multi_agent_pipeline
from app.models import AutomationRunRequest, GenerateRequest, SuiteRequest
from app.services import MultiAgentTestPipeline
from app.services.document_ingestion import DocumentIngestionError, DocumentIngestionService
from app.workflow_models import ScenarioHandoff, Scenarios, Stories, StoryHandoff

router = APIRouter(prefix="/api/workflow", tags=["Five-stage workflow"])


class ExecutionPlanRequest(SuiteRequest):
    request: GenerateRequest


Config = Annotated[Settings, Depends(get_settings)]
Pipeline = Annotated[MultiAgentTestPipeline, Depends(get_multi_agent_pipeline)]


@router.post("/requirements/document")
async def read_document(file: UploadFile, settings: Config) -> dict[str, str]:
    content = await file.read(settings.max_upload_bytes + 1)
    try:
        document = await asyncio.to_thread(
            DocumentIngestionService(max_file_bytes=settings.max_upload_bytes).extract,
            file.filename or "document",
            content,
        )
    except DocumentIngestionError as error:
        raise HTTPException(422, str(error)) from error
    return {"description": document.text, "filename": document.filename}


@router.post("/stories", response_model=Stories)
async def create_stories(request: GenerateRequest, settings: Config) -> Stories:
    try:
        return await WorkflowAgent(settings).stories(request)
    except CopilotGenerationError as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/scenarios", response_model=Scenarios)
async def create_scenarios(request: StoryHandoff, settings: Config) -> Scenarios:
    try:
        return await WorkflowAgent(settings).scenarios(request)
    except CopilotGenerationError as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/test-cases")
async def create_cases(request: ScenarioHandoff, pipeline: Pipeline) -> dict[str, Any]:
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
            422, "Stage handoff is too large. Split requirements into smaller batches."
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
    return execution_plan(request, settings)


@router.post("/execute")
async def execute(request: ExecutionPlanRequest, settings: Config) -> Any:
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


@router.post("/validate-scenarios")
async def validate_scenarios(request: ScenarioHandoff) -> ScenarioHandoff:
    return request
