"""Source-grounded senior BA review, independent of business approval gates."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.agent_instructions import load_agent_instructions, load_profile_instructions
from app.agents import AgentKind, FunctionalAgentDescriptor
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.requirements_validation import BusinessBaseline, Evidence
from app.agents.runner import StructuredAgentDefinition
from app.config import Settings
from app.finance_domain import load_domain_pack
from app.models import GenerateRequest
from app.observability import publish_lifecycle_event
from app.uploaded_brd import verify_brd_receipt

AREAS = (
    "scope_and_objectives",
    "products_and_journeys",
    "business_rules_and_decisions",
    "financial_expectations",
    "data_and_integrations",
    "exceptions_and_controls",
    "acceptance_and_testability",
    "operations_and_non_functional",
)


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BAArea(ReviewModel):
    area: Literal[
        "scope_and_objectives",
        "products_and_journeys",
        "business_rules_and_decisions",
        "financial_expectations",
        "data_and_integrations",
        "exceptions_and_controls",
        "acceptance_and_testability",
        "operations_and_non_functional",
    ]
    status: Literal["covered", "gap", "not_applicable"]
    reason: str = Field(min_length=10, max_length=2000)
    document_quote: str = Field(max_length=2000)


class BAFinding(ReviewModel):
    severity: Literal["blocker", "major", "minor", "info"]
    title: str = Field(min_length=3, max_length=200)
    reason: str = Field(min_length=10, max_length=3000)
    recommendation: str = Field(min_length=10, max_length=3000)
    document_quote: str = Field(max_length=2000)
    evidence: list[Evidence] = Field(max_length=20)


class BAAssessment(ReviewModel):
    outcome: Literal["ready_for_business_review", "needs_clarification", "blocked"]
    summary: str = Field(min_length=20, max_length=4000)
    objectives: list[str] = Field(max_length=30)
    scope: list[str] = Field(max_length=50)
    areas: list[BAArea] = Field(min_length=8, max_length=8)
    findings: list[BAFinding] = Field(max_length=100)
    open_questions: list[str] = Field(max_length=50)
    next_steps: list[str] = Field(max_length=30)


class BAReport(BAAssessment):
    assessed_at: str
    document_fingerprint: str
    knowledge_fingerprint: str
    knowledge_sources: list[dict[str, str]]
    knowledge_limitations: list[str]
    business_approval: Literal["not_granted"] = "not_granted"
    regulatory_compliance: Literal["not_assessed"] = "not_assessed"


class BusinessAnalystAgent:
    descriptor = FunctionalAgentDescriptor(
        id="business-analyst",
        name="BA Agent",
        kind=AgentKind.VALIDATOR,
        purpose="Senior auto-finance business analysis of BRD scope, gaps and readiness.",
        runtime="configured-ai-providers-with-deterministic-evidence-gate",
        capabilities=("brd-review", "domain-analysis", "document-summary", "source-citations"),
        instruction_file=".github/agents/business-analyst.agent.md",
    )

    def __init__(self, settings: Settings):
        self.settings = settings
        self.runner = ArtifactGenerationRunner(settings)

    def knowledge(self) -> tuple[list[dict[str, str]], str, list[str]]:
        sources: list[dict[str, str]] = []
        limitations = []
        path = self.settings.requirements_baseline_path
        try:
            if path.stat().st_size > 500_000:
                raise ValueError("Baseline too large")
            baseline = BusinessBaseline.model_validate_json(path.read_bytes())
            today = datetime.now(UTC).date()
            sources.extend(
                {
                    "id": s.id,
                    "version": s.version,
                    "title": s.title,
                    "authority": "approved_business_source",
                    "owner": s.approved_by,
                    "content": s.content,
                }
                for s in baseline.sources
                if s.status == "approved"
                and s.effective_from <= today
                and (s.expires_on is None or s.expires_on >= today)
            )
        except (OSError, ValueError):
            limitations.append("The approved business baseline is unavailable or invalid.")
        if self.settings.auto_finance_domain_enabled:
            try:
                pack = load_domain_pack(self.settings.auto_finance_domain_path)
                sources.append(
                    {
                        "id": "DOMAIN-CATALOGUE",
                        "version": pack.version,
                        "title": "Auto-finance products and journeys",
                        "authority": "reference_only",
                        "owner": "Configured domain pack",
                        "content": json.dumps(
                            {
                                "market": pack.market,
                                "products": [p.model_dump() for p in pack.products],
                                "journeys": [j.model_dump() for j in pack.journeys],
                            }
                        ),
                    }
                )
                sources.extend(
                    {
                        "id": f"DOMAIN-RULE:{r.id}",
                        "version": r.version,
                        "title": r.id,
                        "authority": "approved_business_source",
                        "owner": r.owner,
                        "content": r.description + "\nSource: " + r.source,
                    }
                    for r in pack.rules
                    if r.status == "approved"
                )
            except (OSError, ValueError):
                limitations.append(
                    "The configured auto-finance domain pack is unavailable or invalid."
                )
        sources.append(
            {
                "id": "DOMAIN-PROFILE",
                "version": "workspace",
                "title": self.settings.agent_profile,
                "authority": "reference_only",
                "owner": "Workspace profile",
                "content": load_profile_instructions(self.settings.agent_profile),
            }
        )
        if not any(s["authority"] == "approved_business_source" for s in sources):
            limitations.append(
                "No effective approved business sources are available; "
                "domain references do not approve pricing or business rules."
            )
        return (
            sources,
            hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest(),
            limitations,
        )

    async def review(self, request: GenerateRequest) -> BAReport:
        if request.uploaded_brd_text or request.uploaded_brd_receipt:
            document = request.uploaded_brd_text or ""
            if (
                not request.uploaded_brd_receipt
                or document not in request.description
                or not verify_brd_receipt(document, request.uploaded_brd_receipt, self.settings)
            ):
                raise HTTPException(422, "BRD verification failed. Upload the document again.")
        publish_lifecycle_event(
            "BA Agent review", "ba_review_source", "success", "BRD source evidence checked."
        )
        sources, fingerprint, limitations = self.knowledge()
        prompt = json.dumps(
            {
                "brd": request.description,
                "candidate_business_rules": [r.model_dump() for r in request.business_rules],
                "additional_context": request.additional_context,
                "knowledge_sources": sources,
                "knowledge_limitations": limitations,
                "required_review_areas": AREAS,
            },
            ensure_ascii=False,
        )
        publish_lifecycle_event(
            "BA Agent review", "ba_review_knowledge", "success", "Domain knowledge prepared."
        )
        source_map = {s["id"]: s["content"] for s in sources}
        document = " ".join(request.description.split())

        def validate(assessment: BAAssessment) -> BAAssessment:
            if {a.area for a in assessment.areas} != set(AREAS):
                raise ValueError("Assess every review area exactly once.")
            for area in assessment.areas:
                if area.status == "covered" and not area.document_quote.strip():
                    raise ValueError("Covered areas require a verified BRD quotation.")
            items: list[BAArea | BAFinding] = [*assessment.areas, *assessment.findings]
            for item in items:
                if item.document_quote and " ".join(item.document_quote.split()) not in document:
                    raise ValueError("A BRD quotation could not be verified.")
            for finding in assessment.findings:
                for evidence in finding.evidence:
                    if evidence.source_id not in source_map or " ".join(
                        evidence.quote.split()
                    ) not in " ".join(source_map[evidence.source_id].split()):
                        raise ValueError("A knowledge citation could not be verified.")
            return assessment

        assessment = await self.runner.generate_structured(
            StructuredAgentDefinition(
                BAAssessment,
                "BA review timed out.",
                "No BA review returned.",
                "Invalid BA review returned.",
            ),
            instructions=load_agent_instructions("business-analyst"),
            prompt=prompt,
            validate=validate,
            llm_model=request.llm_model,
        )
        publish_lifecycle_event(
            "BA Agent review", "ba_review_assessment", "success", "Domain assessment generated."
        )
        validate(assessment)
        if self.knowledge()[1] != fingerprint:
            raise HTTPException(
                409, "Domain knowledge changed during the review. Run BA review again."
            )
        if any(f.severity == "blocker" for f in assessment.findings):
            assessment.outcome = "blocked"
        elif (
            limitations
            or any(a.status == "gap" for a in assessment.areas)
            or any(f.severity == "major" for f in assessment.findings)
            or assessment.open_questions
        ):
            if assessment.outcome == "ready_for_business_review":
                assessment.outcome = "needs_clarification"
        publish_lifecycle_event(
            "BA Agent review",
            "ba_review_evidence",
            "success",
            "Review evidence and outcome checked.",
        )
        publish_lifecycle_event(
            "BA Agent review",
            "validation_basis",
            "passed",
            f"Checked all {len(AREAS)} review areas, required BRD excerpts, "
            "BRD quotation grounding, and cited knowledge quotations against the loaded sources. "
            "Confirmed the knowledge fingerprint did not change during the review. "
            f"Review outcome: {assessment.outcome}. "
            "These are evidence checks, not business approval, "
            "regulatory assessment or test execution.",
        )
        publish_lifecycle_event(
            "BA Agent review",
            "validation_source",
            "info",
            "BRD in the current request; knowledge SHA-256 " + fingerprint + ".",
        )
        cited_ids = {e.source_id for finding in assessment.findings for e in finding.evidence}
        for source in sources:
            publish_lifecycle_event(
                "BA Agent review",
                "validation_source",
                "info",
                f"{source['title']} · {source['id']} · v{source['version']} · "
                f"{source['authority']} · "
                + (
                    "Cited quotation verified."
                    if source["id"] in cited_ids
                    else "Available to review; not cited in findings."
                ),
            )
        return BAReport(
            **assessment.model_dump(),
            assessed_at=datetime.now(UTC).isoformat(),
            document_fingerprint=hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
            knowledge_fingerprint=fingerprint,
            knowledge_sources=[{k: v for k, v in s.items() if k != "content"} for s in sources],
            knowledge_limitations=limitations,
        )
