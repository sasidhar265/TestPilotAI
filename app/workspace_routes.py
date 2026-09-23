"""Workspace rules, language artifacts and activity dashboard endpoints."""

import asyncio
import io
import os
import xml.etree.ElementTree as ET
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.agents.multilanguage_agent import (
    LANGUAGES,
    LanguageArtifact,
    LanguageRequest,
    MultiLanguageAgent,
    safe_files,
)
from app.agents.output_agent import OutputAgent
from app.agents.runner import CopilotGenerationError
from app.automation_layout import validate_layout
from app.config import Settings, get_settings
from app.memory import OrganizationalMemory
from app.models import BusinessRule
from app.observability import (
    generation_cancellations,
    lifecycle_events,
    publish_lifecycle_event,
    request_id_context,
)
from app.services.automation_reports import report_path
from app.services.dashboard import DashboardStore
from app.services.usage import UsageStore
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


@router.get("/workspace/knowledge")
async def knowledge_sources(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    memory = OrganizationalMemory(
        settings.organizational_memory_path,
        enabled=settings.organizational_memory_enabled,
    )
    outputs = OutputAgent(
        settings.organizational_memory_path,
        enabled=settings.organizational_memory_enabled,
    )
    return {
        "enabled": settings.organizational_memory_enabled,
        "suite_count": memory.count(),
        "workflow_counts": memory.workflow_counts(),
        "approved_output_count": outputs.count(),
        "scenario_count": outputs.scenario_count(),
        "suites": memory.entries(),
        "approved_outputs": outputs.entries(),
    }


@router.get("/workspace/knowledge/{source}/{identifier}")
async def knowledge_source_detail(
    source: str,
    identifier: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    memory = OrganizationalMemory(
        settings.organizational_memory_path,
        enabled=settings.organizational_memory_enabled,
    )
    outputs = OutputAgent(
        settings.organizational_memory_path,
        enabled=settings.organizational_memory_enabled,
    )
    detail: dict[str, object] = {
        "suite": memory.entry(identifier) if source == "suites" else None,
        "output": outputs.entry(identifier) if source == "outputs" else None,
    }
    if source not in {"suites", "outputs"} or detail[source[:-1]] is None:
        raise HTTPException(status_code=404, detail="Knowledge source entry not found")
    return detail


@router.get("/automation/languages")
async def languages() -> list[dict[str, str]]:
    return [
        {"id": key, "name": value[0], "framework": value[1], "extension": value[2]}
        for key, value in LANGUAGES.items()
    ]


@router.get("/dashboard")
async def dashboard(
    settings: Annotated[Settings, Depends(get_settings)],
    days: Annotated[int, Query(ge=0, le=90)] = 30,
) -> dict[str, object]:
    snapshot = DashboardStore(settings.organizational_memory_path).snapshot()
    usage = UsageStore(settings.organizational_memory_path)
    for record in snapshot["history"]:
        usage.generation(record)
    snapshot["usage"] = usage.snapshot(days)
    return snapshot


@router.get("/automation/history")
async def automation_history(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    snapshot = DashboardStore(settings.organizational_memory_path).snapshot("repository_checks")
    snapshot["timeout_seconds"] = settings.automation_timeout_seconds
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
    request_id = request_id_context.get()
    lifecycle_events.start(request_id)
    publish_lifecycle_event(
        "Automation pack",
        "pack_generation",
        "running",
        "Generating the automation pack from the approved suite.",
    )
    generation_cancellations.register(request_id, "automation_pack")
    finished = False
    try:
        result = await MultiLanguageAgent(settings).generate(request)
        installed = install_pack_files(result, settings)
        store.finish(
            identifier,
            "completed",
            {"language": result.language, "files": len(result.files), "installed": installed},
        )
        finished = True
        result.notes.append(
            f"Updated configured automation project with {len(installed)} generated files."
        )
        publish_lifecycle_event(
            "Automation pack", "pack_generation", "success", "Pack assembly complete"
        )
        return result
    except asyncio.CancelledError as error:
        publish_lifecycle_event(
            "Automation pack", "pack_generation", "cancelled", "Generation cancelled"
        )
        store.finish(identifier, "cancelled")
        finished = True
        raise HTTPException(499, "Automation pack generation cancelled") from error
    except (ValueError, CopilotGenerationError) as error:
        publish_lifecycle_event(
            "Automation pack", "pack_generation", "failed", "Pack generation failed"
        )
        store.finish(identifier, "failed")
        finished = True
        raise HTTPException(422 if isinstance(error, ValueError) else 503, str(error)) from error
    finally:
        if not finished:
            publish_lifecycle_event(
                "Automation pack", "pack_generation", "failed", "Pack generation failed"
            )
        lifecycle_events.complete(request_id)
        generation_cancellations.unregister(request_id)
        if not finished:
            store.finish(identifier, "failed")


def install_pack_files(artifact: LanguageArtifact, settings: Settings) -> list[str]:
    """Install generated C# files into the configured ReqnRoll project safely."""
    if artifact.language != "csharp":
        return []
    safe_files(artifact)
    validate_layout(artifact.files)
    project = Path(settings.automation_project_path).resolve()
    root = Path.cwd().resolve()
    if project.suffix != ".csproj" or not project.is_file() or root not in project.parents:
        raise ValueError(
            "Configure an existing in-repository ReqnRoll .csproj before generating C#."
        )
    destination_root = project.parent
    manifests = [file for file in artifact.files if file.path.endswith(".csproj")]
    if len(manifests) > 1:
        raise ValueError("Pack must contain a single C# project manifest")
    project_content = merge_project_manifest(project, manifests[0].content) if manifests else None
    # Render normally runs deployment-built binaries. Mark changes before writing any
    # source so even an interrupted installation cannot silently execute the old assembly.
    (destination_root / ".automation-build-required").write_text(uuid4().hex, encoding="utf-8")
    installed: list[str] = []
    for file in artifact.files:
        if file.path.endswith(".csproj") or file.path == "README.md":
            continue
        destination = (destination_root / file.path).resolve()
        if destination_root not in destination.parents or destination == destination_root:
            raise ValueError("Generated file path escapes the configured automation project.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(file.content, encoding="utf-8")
        os.replace(temporary, destination)
        installed.append(file.path)
    if project_content is not None:
        temporary = project.with_suffix(".csproj.tmp")
        temporary.write_text(project_content, encoding="utf-8")
        os.replace(temporary, project)
        installed.append(project.name)
    return installed


def merge_project_manifest(project: Path, generated: str) -> str:
    """Add missing dependencies/configuration while retaining repository project settings."""
    try:
        existing = ET.fromstring(project.read_text(encoding="utf-8"))
        incoming = ET.fromstring(generated)
    except ET.ParseError as error:
        raise ValueError("Invalid C# project manifest") from error
    for group in incoming:
        if group.tag not in {"PropertyGroup", "ItemGroup"} or group.attrib:
            continue
        additions = []
        for item in group:
            if group.tag == "PropertyGroup":
                present = existing.findall(f"PropertyGroup/{item.tag}")
            else:
                identity = item.get("Include") or item.get("Update")
                present = [
                    node
                    for node in existing.findall(f"ItemGroup/{item.tag}")
                    if (node.get("Include") or node.get("Update")) == identity
                ]
            if not present:
                additions.append(deepcopy(item))
        if additions:
            target = ET.SubElement(existing, group.tag)
            target.extend(additions)
    ET.indent(existing, space="  ")
    return ET.tostring(existing, encoding="unicode") + "\n"


@router.post("/step-definitions/languages/download")
async def download(artifact: LanguageArtifact) -> Response:
    # This endpoint archives reviewable user-supplied source; it makes no implementation claim.
    try:
        safe_files(artifact)
        validate_layout(artifact.files)
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
