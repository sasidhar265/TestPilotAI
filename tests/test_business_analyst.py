"""BA readiness and citation checks use isolated provider responses."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.agents.business_analyst import AREAS, BAAssessment, BADomainCheck, BusinessAnalystAgent
from app.agents.requirements_validation import Evidence
from app.config import Settings
from app.domain_knowledge import guide_knowledge_sources
from app.models import GenerateRequest

DOCUMENT = "Quotation requests must reject a negative deposit."


def assessment(topics=("products", "journey", "costs"), document=DOCUMENT):
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
                "document_quote": document,
            }
            for area in AREAS
        ],
        findings=[],
        open_questions=[],
        next_steps=["Review with the business owner"],
        domain_checks=[
            {
                "topic_id": f"UK-AUTO-FINANCE:{topic}",
                "status": "covered",
                "reason": "Fixture assesses selected quotation criteria.",
                "recommendation": "Review applicability to the real BRD before business approval.",
                "document_quote": document,
                "evidence": [
                    {
                        "source_id": f"UK-AUTO-FINANCE:{topic}",
                        "quote": {
                            "products": "Products and UK use cases",
                            "journey": (
                                "Review actual APR, payment count/timing, fees, "
                                "total payable, balloon and offer validity."
                            ),
                            "costs": (
                                "Total customer outlay includes applicable upfront cash, "
                                "scheduled payments, final payment and fees."
                            ),
                        }.get(topic, "Not applicable to this fixture"),
                    }
                ],
            }
            for topic in topics
        ],
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
    assert len(prompt["required_domain_topics"]) == 3
    assert report.domain_validation.topics_reviewed == 3
    assert report.domain_validation.evidence_verified is True


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


def test_ba_domain_gap_uses_shared_guide_and_requires_clarification(tmp_path):
    reviewer = agent(tmp_path, approved=True)
    source = next(s for s in guide_knowledge_sources() if s["id"] == "UK-AUTO-FINANCE:products")
    value = assessment()
    value.domain_checks[0] = BADomainCheck(
        topic_id=source["id"],
        status="gap",
        gap_origin="brd",
        reason="The quotation BRD does not identify the ownership and final-payment structure.",
        recommendation="Ask the product owner to supply the applicable finance product definition.",
        document_quote=DOCUMENT,
        evidence=[{"source_id": source["id"], "quote": "Personal Contract Purchase"}],
    )
    reviewer.runner.generate_structured = AsyncMock(return_value=value)
    report = asyncio.run(
        reviewer.review(GenerateRequest(description=DOCUMENT, finance_product_id="PCP"))
    )
    assert report.outcome == "needs_clarification"
    assert report.domain_validation.status == "needs_clarification"
    assert report.domain_validation.gaps == 1
    assert report.domain_validation.evidence_verified
    assert report.domain_checks[0].topic_id == source["id"]
    prompt = json.loads(reviewer.runner.generate_structured.call_args.kwargs["prompt"])
    supplied = next(s for s in prompt["knowledge_sources"] if s["id"] == source["id"])
    assert "Personal Contract Purchase" in supplied["content"]
    assert "Business Contract Hire" not in supplied["content"]
    assert supplied["authority"] == "reference_only"
    metadata = next(s for s in report.knowledge_sources if s["id"] == source["id"])
    assert metadata["path"].endswith("#products")
    assert len(metadata["fingerprint"]) == 64


@pytest.mark.parametrize(
    "kind",
    [
        "missing",
        "duplicate",
        "no_citation",
        "fake_citation",
        "blank_citation",
        "fake_brd",
        "selected_scope",
    ],
)
def test_ba_domain_report_rejects_incomplete_or_unverifiable_checks(tmp_path, kind):
    reviewer = agent(tmp_path, approved=True)
    value = assessment()
    request = GenerateRequest(description=DOCUMENT)
    if kind == "missing":
        value.domain_checks.pop()
    elif kind == "duplicate":
        value.domain_checks[1].topic_id = value.domain_checks[0].topic_id
    elif kind == "selected_scope":
        request = request.model_copy(update={"finance_product_id": "PCP"})
        value.domain_checks[0].status = "not_applicable"
    else:
        check = value.domain_checks[0]
        check.status = "covered"
        check.evidence = []
        check.document_quote = DOCUMENT if kind != "fake_brd" else "Invented BRD statement."
        if kind != "no_citation":
            check.evidence = [Evidence(source_id=check.topic_id, quote="Products and UK use cases")]
        if kind == "fake_citation":
            check.evidence[0].quote = "Invented domain statement."
        if kind == "blank_citation":
            check.evidence[0].quote = " " * 20
    reviewer.runner.generate_structured = AsyncMock(return_value=value)
    with pytest.raises(ValueError):
        asyncio.run(reviewer.review(request))


def test_guide_reference_change_invalidates_inflight_ba_review(tmp_path, monkeypatch):
    reviewer = agent(tmp_path, approved=True)
    sources = guide_knowledge_sources(include_units=True)

    async def changed_guide(*args, **kwargs):
        changed = [dict(s) for s in sources]
        target = next(s for s in changed if s["id"].endswith(":costs"))
        units = json.loads(target["units"])
        units[0]["content"] += "\nChanged reference during review."
        target["units"] = json.dumps(units)
        monkeypatch.setattr(
            "app.agents.business_analyst.guide_knowledge_sources", lambda **kwargs: changed
        )
        return assessment()

    reviewer.runner.generate_structured = changed_guide
    with pytest.raises(HTTPException) as error:
        asyncio.run(reviewer.review(GenerateRequest(description=DOCUMENT)))
    assert error.value.status_code == 409


def test_ba_selected_product_is_grounded_and_reported(tmp_path):
    reviewer = agent(tmp_path, approved=True)
    value = assessment()
    check = value.domain_checks[0]
    check.status = "gap"
    check.gap_origin = "domain_knowledge"
    check.evidence = [Evidence(source_id=check.topic_id, quote="Personal Contract Purchase")]
    reviewer.runner.generate_structured = AsyncMock(return_value=value)
    report = asyncio.run(
        reviewer.review(GenerateRequest(description=DOCUMENT, finance_product_id="PCP"))
    )
    assert report.domain_scope["product"] == "PCP"
    assert report.domain_validation.gaps == 1
    prompt = json.loads(reviewer.runner.generate_structured.call_args.kwargs["prompt"])
    assert "AUTO-FINANCE DOMAIN PACK" in prompt["additional_context"]
    assert prompt["selected_domain_scope"]["product"] == "PCP"


def test_disabled_domain_scope_stops_ba_before_provider_call(tmp_path):
    reviewer = agent(tmp_path)
    reviewer.settings = reviewer.settings.model_copy(update={"auto_finance_domain_enabled": False})
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            reviewer.review(GenerateRequest(description=DOCUMENT, finance_product_id="PCP"))
        )
    assert error.value.status_code == 422
    reviewer.runner.generate_structured.assert_not_awaited()


def test_alignment_excludes_outside_scope_and_missing_knowledge():
    from app.agents.business_analyst import BADomainCheck, alignment_metrics

    def check(status, origin="none"):
        return BADomainCheck(
            topic_id="fixture",
            status=status,
            gap_origin=origin,
            reason="Fixture assesses the scoped criterion.",
            recommendation="Confirm the applicable approved criteria.",
            document_quote=DOCUMENT,
        )

    metrics = alignment_metrics(
        [
            check("covered"),
            check("covered"),
            check("gap", "brd"),
            check("gap", "domain_knowledge"),
            check("not_applicable"),
        ]
    )
    assert metrics["alignment_percent"] == 66.7
    assert metrics["alignment_assessable"] == 3
    assert metrics["alignment_unassessable"] == 1
    assert alignment_metrics([])["alignment_percent"] is None
    assert alignment_metrics([check("conflict")])["alignment_percent"] == 0
