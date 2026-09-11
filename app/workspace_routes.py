"""Workspace rules, language artifacts and activity dashboard endpoints."""

import asyncio
import io
import zipfile
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.agents.multilanguage_agent import (
    LANGUAGES,
    LanguageArtifact,
    LanguageRequest,
    MultiLanguageAgent,
    safe_files,
)
from app.agents.runner import CopilotGenerationError
from app.config import Settings, get_settings
from app.models import BusinessRule
from app.observability import generation_cancellations, request_id_context
from app.services.automation_reports import report_path
from app.services.dashboard import DashboardStore
from app.workspace_policy import load_business_rules, save_business_rules, standards

router = APIRouter(prefix="/api")


class SharedRules(BaseModel):
    business_rules: list[BusinessRule] = Field(max_length=100)


@router.get("/workspace/rules")
async def read_rules() -> SharedRules:
    try:
        return SharedRules(business_rules=load_business_rules())
    except (OSError, ValueError) as error:
        raise HTTPException(422, "Shared rules file is missing or invalid") from error


@router.put("/workspace/rules")
async def write_rules(request: SharedRules) -> SharedRules:
    try:
        save_business_rules(request.business_rules)
        return request
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/workspace/standards")
async def read_standards() -> dict[str, str]:
    return {"automation": standards("automation"), "feature": standards("feature")}


@router.get("/automation/languages")
async def languages() -> list[dict[str, str]]:
    return [
        {"id": key, "name": value[0], "framework": value[1], "extension": value[2]}
        for key, value in LANGUAGES.items()
    ]


@router.get("/dashboard")
async def dashboard(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, object]:
    return DashboardStore(settings.organizational_memory_path).snapshot()


@router.get("/automation/history")
async def automation_history(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    snapshot = DashboardStore(settings.organizational_memory_path).snapshot("repository_checks")
    for item in snapshot["history"]:
        details = item.get("details", {})
        identifier = details.get("report_id")
        details["report_available"] = bool(
            identifier and report_path(settings, identifier).is_file()
        )
    return snapshot


@router.get("/automation/reports/{identifier}")
async def download_automation_report(
    identifier: str, settings: Annotated[Settings, Depends(get_settings)]
) -> FileResponse:
    try:
        path = report_path(settings, identifier)
    except ValueError as error:
        raise HTTPException(404, "Report not found") from error
    if not path.is_file():
        raise HTTPException(404, "Report not found or no longer retained")
    return FileResponse(
        path,
        media_type="text/html",
        filename=f"bdd-allure-{identifier}.html",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/step-definitions/languages/bindings", response_model=LanguageArtifact)
async def bindings(
    request: LanguageRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> LanguageArtifact:
    try:
        return MultiLanguageAgent(settings).bindings(request)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/step-definitions/languages/pack", response_model=LanguageArtifact)
async def pack(
    request: LanguageRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> LanguageArtifact:
    store = DashboardStore(settings.organizational_memory_path)
    identifier = store.start("automation_pack")
    generation_cancellations.register(request_id_context.get(), "automation_pack")
    try:
        result = await MultiLanguageAgent(settings).generate(request)
        store.finish(
            identifier, "completed", {"language": result.language, "files": len(result.files)}
        )
        return result
    except asyncio.CancelledError as error:
        store.finish(identifier, "cancelled")
        raise HTTPException(499, "Automation pack generation cancelled") from error
    except (ValueError, CopilotGenerationError) as error:
        store.finish(identifier, "failed")
        raise HTTPException(422 if isinstance(error, ValueError) else 503, str(error)) from error
    finally:
        generation_cancellations.unregister(request_id_context.get())
        store.finish(identifier, "failed")


@router.post("/step-definitions/languages/download")
async def download(artifact: LanguageArtifact) -> Response:
    # This endpoint archives reviewable user-supplied source; it makes no implementation claim.
    try:
        safe_files(artifact)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in artifact.files:
            archive.writestr(file.path, file.content)
    return Response(
        output.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="automation-{artifact.language}.zip"'
        },
    )
