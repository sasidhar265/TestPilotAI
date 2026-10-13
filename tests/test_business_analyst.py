"""BA readiness and citation checks use isolated provider responses."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.agents.business_analyst import AREAS, BAAssessment, BusinessAnalystAgent
from app.config import Settings
from app.models import GenerateRequest

DOCUMENT = "Quotation requests must reject a negative deposit."


def assessment():
    return BAAssessment(
        outcome="ready_for_business_review",
        summary="The BRD describes deposit validation for a quotation.",
        objectives=["Validate supplied deposit"],
        scope=["Quotation validation"],
        areas=[
            {
                "area": area,
                "status": "covered",
                "reason": "The supplied document covers this area.",
                "document_quote": DOCUMENT,
            }
            for area in AREAS
        ],
        findings=[],
        open_questions=[],
        next_steps=["Review with the business owner"],
    )


def agent(tmp_path, approved=False):
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "id": "POLICY",
                        "version": "1",
                        "title": "Deposit policy",
                        "status": "approved",
                        "approved_by": "Business owner",
                        "effective_from": "2020-01-01",
                        "expires_on": None,
                        "content": DOCUMENT,
                    }
                ]
                if approved
                else []
            }
        )
    )
    result = BusinessAnalystAgent(Settings(requirements_baseline_path=path))
    result.runner.generate_structured = AsyncMock(return_value=assessment())
    return result


def test_ba_summary_without_approved_sources_does_not_claim_readiness(tmp_path):
    reviewer = agent(tmp_path)
    report = asyncio.run(reviewer.review(GenerateRequest(description=DOCUMENT)))
    assert report.outcome == "needs_clarification"
    assert report.business_approval == "not_granted"
    assert report.regulatory_compliance == "not_assessed"
    assert report.knowledge_limitations
    assert all("content" not in s for s in report.knowledge_sources)
    prompt = json.loads(reviewer.runner.generate_structured.call_args.kwargs["prompt"])
    assert prompt["brd"] == DOCUMENT
    assert prompt["knowledge_sources"]


def test_verified_business_knowledge_can_support_owner_review(tmp_path):
    report = asyncio.run(
        agent(tmp_path, approved=True).review(GenerateRequest(description=DOCUMENT))
    )
    assert report.outcome == "ready_for_business_review"
    assert any(s["id"] == "POLICY" for s in report.knowledge_sources)


@pytest.mark.parametrize("kind", ["document_quote", "evidence", "coverage"])
def test_ba_rejects_fabricated_citations_and_incomplete_coverage(tmp_path, kind):
    reviewer = agent(tmp_path, approved=True)
    value = assessment()
    if kind == "document_quote":
        value.areas[0].document_quote = "Invented expected behavior."
    elif kind == "coverage":
        value.areas[1].area = value.areas[0].area
    else:
        from app.agents.business_analyst import BAFinding

        value.findings = [
            BAFinding(
                severity="major",
                title="Unsupported citation",
                reason="The returned citation does not exist.",
                recommendation="Obtain the actual approved business source.",
                document_quote=DOCUMENT,
                evidence=[{"source_id": "POLICY", "quote": "Invented policy quotation"}],
            )
        ]
    reviewer.runner.generate_structured = AsyncMock(return_value=value)
    with pytest.raises(ValueError):
        asyncio.run(reviewer.review(GenerateRequest(description=DOCUMENT)))


def test_ba_rejects_forged_upload_before_calling_provider(tmp_path):
    reviewer = agent(tmp_path)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            reviewer.review(
                GenerateRequest(
                    description=DOCUMENT, uploaded_brd_text=DOCUMENT, uploaded_brd_receipt="fake"
                )
            )
        )
    assert error.value.status_code == 422
    reviewer.runner.generate_structured.assert_not_awaited()


@pytest.mark.parametrize("provider", ["codex", "openai"])
def test_ba_review_preserves_explicit_provider(tmp_path, provider):
    reviewer = agent(tmp_path)
    asyncio.run(reviewer.review(GenerateRequest(description=DOCUMENT, llm_model=provider)))
    assert reviewer.runner.generate_structured.call_args.kwargs["llm_model"] == provider


def test_ba_review_publishes_evidence_checks_and_distinguishes_available_sources(
    tmp_path, monkeypatch
):
    events = []
    monkeypatch.setattr(
        "app.agents.business_analyst.publish_lifecycle_event", lambda *event: events.append(event)
    )
    reviewer = agent(tmp_path, approved=True)
    report = asyncio.run(reviewer.review(GenerateRequest(description=DOCUMENT)))
    basis = next(event for event in events if event[1] == "validation_basis")
    assert basis[2] == "passed"
    assert "BRD quotation grounding" in basis[3]
    assert "knowledge fingerprint" in basis[3]
    sources = [event[3] for event in events if event[1] == "validation_source"]
    assert any("POLICY" in source and "not cited" in source for source in sources)
    assert any("reference_only" in source for source in sources)
    assert report.business_approval == "not_granted"
