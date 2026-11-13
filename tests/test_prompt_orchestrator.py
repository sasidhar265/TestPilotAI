"""Intent understanding selects the user's outcome without a default story workflow."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.prompt_orchestrator import PromptIntent, PromptOrchestrator
from app.config import Settings
from app.main import app
from app.models import GenerateRequest, LlmModel
from app.services.website_inspection import WebsiteInspection, WebsiteInspectionService, WebsitePage


@pytest.mark.parametrize("workflow", ["stories", "test-cases", "business-analysis", "clarify"])
def test_intent_endpoint_uses_structured_ai_and_selected_provider(monkeypatch, workflow):
    calls = []

    async def understand(self, definition, **kwargs):
        calls.append(kwargs)
        return PromptIntent(workflow=workflow, summary="Interpret the actual requested outcome.")

    monkeypatch.setattr(ArtifactGenerationRunner, "generate_structured", understand)
    with TestClient(app) as client:
        response = client.post(
            "/api/workflow/intent",
            json={
                "description": "Please help me understand this supplied requirement.",
                "llm_model": "codex",
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["workflow"] == workflow
    assert calls[0]["llm_model"] == LlmModel.CODEX
    assert "Do not assume that every input asks for stories" in calls[0]["instructions"]
    if workflow == "clarify":
        assert response.json()["questions"]


@pytest.mark.asyncio
async def test_questions_prevent_generation(monkeypatch):
    async def understand(self, definition, **kwargs):
        return PromptIntent(
            workflow="stories",
            summary="The desired artifact is ambiguous.",
            questions=["Would you like test cases or a requirements review?"],
        )

    monkeypatch.setattr(ArtifactGenerationRunner, "generate_structured", understand)
    pipeline = SimpleNamespace(run=AsyncMock())
    result = await PromptOrchestrator(Settings()).run(
        GenerateRequest(description="A user can search for roles."),
        pipeline,
    )
    assert result.intent.workflow == "clarify"
    pipeline.run.assert_not_called()
    assert not result.result


@pytest.mark.asyncio
async def test_explicit_test_case_dispatch_skips_story_generation():
    suite = SimpleNamespace(model_dump=lambda **kwargs: {"test_cases": []})
    validation = SimpleNamespace(model_dump=lambda **kwargs: {"passed": True})
    pipeline = SimpleNamespace(
        run=AsyncMock(return_value=SimpleNamespace(suite=suite, validation=validation))
    )
    result = await PromptOrchestrator(Settings()).run(
        GenerateRequest(
            description="Design regression test cases for these approved requirements.",
            requested_workflow="test-cases",
            interpret_prompt=True,
        ),
        pipeline,
    )
    pipeline.run.assert_awaited_once()
    assert result.intent.workflow == "test-cases"
    assert result.result["validation"]["passed"]


def test_semantic_framework_dispatch_does_not_require_keyword_command(monkeypatch):
    async def understand(self, definition, **kwargs):
        return PromptIntent(
            workflow="website-framework", summary="Prepare a reusable Selenium test project."
        )

    async def inspect(self, request, settings):
        return WebsiteInspection(
            pages=[
                WebsitePage(url=request.url, title="Careers", headings=[], controls=[], links=[])
            ],
            warnings=[],
            description="Observed Careers page.",
        )

    monkeypatch.setattr(ArtifactGenerationRunner, "generate_structured", understand)
    monkeypatch.setattr(WebsiteInspectionService, "inspect", inspect)
    with TestClient(app) as client:
        response = client.post(
            "/api/agent/run",
            json={
                "description": (
                    "I need a reusable C# Selenium setup for https://example.com "
                    "with BDD page objects."
                ),
                "interpret_prompt": True,
            },
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["workflow"] == "prompt-result"
    assert result["intent"]["workflow"] == "website-framework"
    assert result["result"]["archive_base64"]
