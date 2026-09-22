"""Business evidence gating; providers are isolated from deterministic enforcement tests."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.agents.requirements_validation import (
    AlignmentAssessment,
    RequirementsBlocked,
    RequirementsValidationAgent,
)
from app.config import Settings
from app.memory import OrganizationalMemory
from app.models import GenerateRequest
from app.services import MultiAgentTestPipeline, RequirementToTestCaseService, TestGenerationService
from app.uploaded_brd import issue_brd_receipt

SOURCE = "Quotation requests must reject a negative deposit."
REQUEST = GenerateRequest(description=SOURCE)


def baseline(tmp_path, *, status="approved"):
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "BR-TEST-001",
                        "version": "1",
                        "title": "Synthetic test business rule",
                        "status": status,
                        "approved_by": "Test fixture owner",
                        "effective_from": "2020-01-01",
                        "expires_on": None,
                        "content": SOURCE,
                    }
                ]
            }
        )
    )
    return path


def assessment(status="aligned", *, quote=SOURCE, identifier="REQ-001"):
    return AlignmentAssessment.model_validate(
        {
            "findings": [
                {
                    "requirement_id": identifier,
                    "status": status,
                    "reason": "Matches the supplied test rule.",
                    "suggested_change": ""
                    if status == "aligned"
                    else "Resolve the conflicting behavior.",
                    "evidence": [{"source_id": "BR-TEST-001", "quote": quote}],
                }
            ]
        }
    )


def agent(tmp_path, **kwargs):
    path = baseline(tmp_path, **kwargs)
    instance = RequirementsValidationAgent(
        Settings(_env_file=None, requirements_baseline_path=path)
    )
    instance.runner = SimpleNamespace(generate_structured=AsyncMock(return_value=assessment()))
    return instance


@pytest.mark.asyncio
async def test_aligned_source_has_verifiable_receipt(tmp_path):
    instance = agent(tmp_path)
    report = await instance.require(REQUEST)
    assert report.status == "aligned"
    assert report.regulatory_compliance == "not_assessed"
    assert report.sources[0]["version"] == "1"
    assert len(report.request_fingerprint) == len(report.baseline_fingerprint) == 64


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "retired"])
async def test_unapproved_sources_never_contact_provider(tmp_path, status):
    instance = agent(tmp_path, status=status)
    with pytest.raises(RequirementsBlocked) as error:
        await instance.require(REQUEST)
    assert error.value.status_code == 422
    assert "no effective approved" in error.value.report.message
    instance.runner.generate_structured.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["expired", "future", "missing", "malformed", "empty"])
async def test_unavailable_baseline_blocks(tmp_path, change):
    instance = agent(tmp_path)
    path = instance.settings.requirements_baseline_path
    data = json.loads(path.read_text())
    if change == "expired":
        data["sources"][0]["expires_on"] = "2020-01-02"
    elif change == "future":
        data["sources"][0]["effective_from"] = "2999-01-01"
    elif change == "empty":
        data["sources"] = []
    if change == "missing":
        instance.settings.requirements_baseline_path = tmp_path / "absent.json"
    else:
        path.write_text("invalid" if change == "malformed" else json.dumps(data))
    with pytest.raises(RequirementsBlocked):
        await instance.require(REQUEST)
    instance.runner.generate_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_uploaded_brd_can_source_workflow_when_baseline_is_empty(tmp_path):
    instance = agent(tmp_path)
    instance.settings.requirements_baseline_path.write_text('{"sources": []}')
    document = "Quotation requests must reject a negative deposit."
    request = GenerateRequest(
        description="Generate tests for PCP quotations.\n\n" + document,
        uploaded_brd_text=document,
        uploaded_brd_receipt=issue_brd_receipt(document, instance.settings),
    )
    report = await instance.require(request)
    assert report.status == "aligned"
    assert report.sources[0]["status"] == "user_provided"
    assert "Business approval" in report.message
    instance.runner.generate_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_uploaded_brd_receipt_cannot_authorize_changed_text(tmp_path):
    instance = agent(tmp_path)
    instance.settings.requirements_baseline_path.write_text('{"sources": []}')
    document = "Quotation requests must reject a negative deposit."
    request = GenerateRequest(
        description="Quotation requests may accept a negative deposit.",
        uploaded_brd_text=document,
        uploaded_brd_receipt=issue_brd_receipt(document, instance.settings),
    )
    with pytest.raises(RequirementsBlocked) as error:
        await instance.require(request)
    assert "verification failed" in error.value.report.message


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["conflict", "needs_clarification", "out_of_scope"])
async def test_non_aligned_decisions_block(tmp_path, status):
    instance = agent(tmp_path)
    instance.runner.generate_structured.return_value = assessment(status)
    with pytest.raises(RequirementsBlocked) as error:
        await instance.require(REQUEST)
    assert error.value.report.findings[0].status == status


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["citation", "omission", "duplicate", "provider", "revoked"])
async def test_incomplete_or_unverifiable_analysis_fails_closed(tmp_path, failure):
    instance = agent(tmp_path)
    request = REQUEST
    if failure == "citation":
        instance.runner.generate_structured.return_value = assessment(
            quote="Invented authority text."
        )
    elif failure == "omission":
        request = REQUEST.model_copy(update={"additional_context": "Also allow negative deposits."})
    elif failure == "duplicate":
        result = assessment()
        result.findings *= 2
        instance.runner.generate_structured.return_value = result
    elif failure == "provider":
        instance.runner.generate_structured.side_effect = RuntimeError("Provider unavailable")
    else:

        async def revoke(*args, **kwargs):
            instance.settings.requirements_baseline_path.write_text('{"sources": []}')
            return assessment()

        instance.runner.generate_structured.side_effect = revoke
    with pytest.raises(RequirementsBlocked):
        await instance.require(request)


@pytest.mark.asyncio
async def test_cancellation_is_not_swallowed(tmp_path):
    instance = agent(tmp_path)
    instance.runner.generate_structured.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await instance.require(REQUEST)


@pytest.mark.asyncio
async def test_pipeline_blocks_before_cached_reuse_and_generation(tmp_path):
    instance = agent(tmp_path, status="draft")
    memory = OrganizationalMemory(tmp_path / "memory.db")
    pipeline = MultiAgentTestPipeline(
        Mock(), Mock(), Mock(), SimpleNamespace(memory=memory), requirements_validator=instance
    )
    pipeline.knowledge.recall = Mock()
    with pytest.raises(RequirementsBlocked):
        await pipeline.run(REQUEST)
    pipeline.knowledge.recall.assert_not_called()
    pipeline.generator.generate.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("service_type", [TestGenerationService, RequirementToTestCaseService])
async def test_legacy_generation_and_expansion_cannot_bypass(tmp_path, service_type):
    from app.models import ExpandRequest

    registry = Mock()
    instance = agent(tmp_path, status="draft")
    service = service_type(registry, OrganizationalMemory(tmp_path / "memory.db"), instance)
    operation = service.generate if service_type is TestGenerationService else service.convert
    with pytest.raises(RequirementsBlocked):
        await operation(REQUEST)
    with pytest.raises(RequirementsBlocked):
        await service.expand(ExpandRequest(request=REQUEST, existing_titles=["Existing case"]))
    registry.get_test_design_agent.assert_not_called()
    registry.get_requirement_to_test_case_agent.assert_not_called()
