import asyncio
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app import workspace_routes
from app.agents.multilanguage_agent import ArtifactFile, LanguageArtifact, MultiLanguageAgent
from app.config import Settings
from app.observability import LifecycleEventRegistry, lifecycle_events, request_id_context


def test_manifest_keeps_settings_and_adds_missing_dependencies(tmp_path):
    project = tmp_path / "Existing.csproj"
    original = (
        "<Project><PropertyGroup><RunSettingsFilePath>custom.runsettings</RunSettingsFilePath>"
        '</PropertyGroup><ItemGroup><PackageReference Include="NUnit" Version="4.3.2" />'
        "</ItemGroup></Project>"
    )
    project.write_text(original)
    incoming = (
        "<Project><PropertyGroup><RunSettingsFilePath>generated.runsettings</RunSettingsFilePath>"
        '</PropertyGroup><ItemGroup><PackageReference Include="NUnit" Version="4.0.0" />'
        '<PackageReference Include="Microsoft.Extensions.Http" Version="8.0.0" />'
        "</ItemGroup></Project>"
    )
    merged = workspace_routes.merge_project_manifest(project, incoming)
    root = ET.fromstring(merged)
    assert root.findtext("PropertyGroup/RunSettingsFilePath") == "custom.runsettings"
    assert {
        p.get("Include"): p.get("Version") for p in root.findall("ItemGroup/PackageReference")
    } == {"NUnit": "4.3.2", "Microsoft.Extensions.Http": "8.0.0"}
    project.write_text(merged)
    assert workspace_routes.merge_project_manifest(project, incoming) == merged


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failed", "cancelled"])
async def test_pack_terminal_events_match_result(tmp_path, monkeypatch, outcome):
    request_id = f"pack-terminal-{outcome}"
    token = request_id_context.set(request_id)
    artifact = LanguageArtifact(
        language="python",
        framework="Behave",
        files=[ArtifactFile(path="README.md", content="ready")],
    )
    error = {
        "failed": ValueError("Invalid implementation"),
        "cancelled": asyncio.CancelledError(),
    }.get(outcome)
    monkeypatch.setattr(
        MultiLanguageAgent, "generate", AsyncMock(return_value=artifact, side_effect=error)
    )
    monkeypatch.setattr(workspace_routes, "install_pack_files", lambda *args: [])
    try:
        settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
        if error is None:
            await workspace_routes.pack(None, settings)
        else:
            with pytest.raises(HTTPException):
                await workspace_routes.pack(None, settings)
        events = lifecycle_events.read(request_id)
        assert events["complete"]
        assert events["events"][-1]["status"] == outcome
    finally:
        request_id_context.reset(token)


@pytest.mark.asyncio
async def test_files_are_only_announced_after_generation(monkeypatch):
    token = request_id_context.set("real-file-progress")
    artifact = LanguageArtifact(
        language="python",
        framework="Behave",
        files=[ArtifactFile(path="README.md", content="ready")],
    )

    async def generate(self, request):
        events = lifecycle_events.read("real-file-progress")["events"]
        assert not any(event["action"] == "file_generated" for event in events)
        return artifact

    monkeypatch.setattr(MultiLanguageAgent, "_generate", generate)
    try:
        assert await MultiLanguageAgent(Settings(_env_file=None)).generate(None) == artifact
        events = lifecycle_events.read("real-file-progress")["events"]
        files = [event for event in events if event["action"] == "file_generated"]
        assert len(files) == 1
        assert files[0]["status"] == "success"
    finally:
        request_id_context.reset(token)


def test_progress_retains_maximum_pack_file_count():
    registry = LifecycleEventRegistry()
    for index in range(105):
        registry.publish("pack", "Automation pack", "file_generated", "success", str(index))
    assert len(registry.read("pack")["events"]) == 105


def test_install_updates_configured_project_and_preserves_existing_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "automation"
    root.mkdir()
    project = root / "Existing.csproj"
    project.write_text(
        "<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>"
    )
    existing = root / "Features" / "Existing.feature"
    existing.parent.mkdir()
    existing.write_text("Feature: Existing\n")
    artifact = LanguageArtifact(
        language="csharp",
        framework="ReqnRoll",
        files=[
            ArtifactFile(
                path="Automation.csproj",
                content=(
                    '<Project><ItemGroup><PackageReference Include="Microsoft.Extensions.Http" '
                    'Version="8.0.0" /></ItemGroup></Project>'
                ),
            ),
            ArtifactFile(path="Reqnroll/Automation.runsettings", content="<RunSettings />"),
        ],
    )
    installed = workspace_routes.install_pack_files(
        artifact, Settings(_env_file=None, automation_project_path=project)
    )
    assert "Existing.csproj" in installed
    assert not (root / "Automation.csproj").exists()
    assert "Microsoft.Extensions.Http" in project.read_text()
    assert existing.read_text() == "Feature: Existing\n"
