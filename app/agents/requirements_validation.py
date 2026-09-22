"""Fail-closed business alignment assessment against server-owned approved sources."""

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent_instructions import load_agent_instructions, load_profile_instructions
from app.agents import AgentKind, FunctionalAgentDescriptor
from app.agents.runner import StructuredAgentDefinition
from app.config import Settings, get_settings
from app.models import GenerateRequest
from app.observability import publish_lifecycle_event
from app.workspace_policy import apply_rules


class BusinessSource(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    status: Literal["draft", "approved", "retired"]
    approved_by: str = Field(max_length=200)
    effective_from: date
    expires_on: date | None
    content: str = Field(min_length=10, max_length=50000)

    @model_validator(mode="after")
    def approval_metadata(self) -> "BusinessSource":
        if self.status == "approved" and len(self.approved_by) < 2:
            raise ValueError("Approved sources require an accountable reviewer")
        if self.expires_on and self.expires_on < self.effective_from:
            raise ValueError("Source expiry precedes its effective date")
        return self


class BusinessBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[BusinessSource] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_sources(self) -> "BusinessBaseline":
        if len({s.id for s in self.sources}) != len(self.sources):
            raise ValueError("Business source IDs must be unique")
        return self


class Evidence(BaseModel):
    source_id: str
    quote: str = Field(min_length=10, max_length=3000)


class RequirementFinding(BaseModel):
    requirement_id: str
    status: Literal["aligned", "conflict", "needs_clarification", "out_of_scope"]
    reason: str = Field(min_length=10, max_length=3000)
    suggested_change: str = Field(max_length=3000)
    evidence: list[Evidence] = Field(max_length=20)


class AlignmentAssessment(BaseModel):
    findings: list[RequirementFinding] = Field(min_length=1, max_length=1000)


class RequirementsReport(BaseModel):
    status: Literal["aligned", "blocked"]
    message: str
    request_fingerprint: str
    baseline_fingerprint: str
    assessed_at: str
    sources: list[dict[str, str]]
    findings: list[RequirementFinding]
    requirements: dict[str, str]
    regulatory_compliance: Literal["not_assessed"] = "not_assessed"


class RequirementsBlocked(HTTPException):
    def __init__(self, report: RequirementsReport):
        self.report = report
        super().__init__(
            422,
            detail={
                "code": "REQUIREMENTS_NOT_ALIGNED",
                "message": report.message,
                "requirements_validation": report.model_dump(mode="json"),
            },
        )


class RequirementsValidationAgent:
    descriptor = FunctionalAgentDescriptor(
        id="requirements-validation-agent",
        name="Requirements Validation Agent",
        kind=AgentKind.VALIDATOR,
        purpose="Gate generation and execution on approved business alignment.",
        runtime="configured-ai-providers-with-deterministic-evidence-gate",
        capabilities=(
            "business-alignment",
            "source-citations",
            "conflict-detection",
            "fail-closed-gate",
        ),
        instruction_file=".github/agents/requirements-validation.agent.md",
    )

    def __init__(self, settings: Settings | None = None):
        from app.agents.artifact_runner import ArtifactGenerationRunner

        self.settings = settings or get_settings()
        self.runner = ArtifactGenerationRunner(self.settings)

    async def assess(self, request: GenerateRequest) -> RequirementsReport:
        # Supplied rules are candidate requirements, never approval evidence.
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        baseline_fingerprint = "unavailable"
        source_metadata: list[dict[str, str]] = []
        units: dict[str, str] = {}

        def report(
            message: str, findings: list[RequirementFinding] | None = None
        ) -> RequirementsReport:
            result = RequirementsReport(
                status="blocked",
                message=message,
                request_fingerprint=fingerprint,
                baseline_fingerprint=baseline_fingerprint,
                assessed_at=datetime.now(UTC).isoformat(),
                sources=source_metadata,
                findings=findings or [],
                requirements=units,
            )
            return result

        publish_lifecycle_event(
            "Requirements Validation Agent",
            "business_alignment",
            "running",
            "Checking requirements against approved business sources.",
        )
        try:
            request = apply_rules(request)
            fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
            chunks = [line.strip() for line in request.description.splitlines() if line.strip()]
            chunks.extend(f"{rule.id}: {rule.description}" for rule in request.business_rules)
            if request.additional_context.strip():
                chunks.append(request.additional_context.strip())
            units = {f"REQ-{index:03d}": text for index, text in enumerate(chunks, 1)}
            if len(units) > 1000:
                return report(
                    "Requirements blocked: split this source into at most 1,000 lines and rules."
                )
            path = self.settings.requirements_baseline_path
            if path.stat().st_size > 500_000:
                return report("Requirements blocked: approved business baseline exceeds 500 KB.")
            raw = path.read_bytes()
            baseline_fingerprint = hashlib.sha256(raw).hexdigest()
            baseline = BusinessBaseline.model_validate_json(raw)
            today = datetime.now(UTC).date()
            sources = [
                s
                for s in baseline.sources
                if s.status == "approved"
                and s.effective_from <= today
                and (s.expires_on is None or s.expires_on >= today)
            ]
            source_metadata = [
                {"id": s.id, "version": s.version, "title": s.title, "approved_by": s.approved_by}
                for s in sources
            ]
            if not sources:
                return report(
                    "Requirements blocked: no effective approved business sources are configured. "
                    "Have the business owner approve and populate the requirements baseline."
                )
            instructions = load_agent_instructions("requirements-validation")
            context = load_profile_instructions(self.settings.agent_profile)
            prompt = json.dumps(
                {
                    "requirements": units,
                    "approved_sources": [s.model_dump(mode="json") for s in sources],
                    "domain_reference_only": context,
                },
                ensure_ascii=False,
            )
            assessment = await self.runner.generate_structured(
                StructuredAgentDefinition(
                    AlignmentAssessment,
                    "Requirements analysis timed out.",
                    "No requirements assessment returned.",
                    "Invalid requirements assessment.",
                ),
                instructions=instructions,
                prompt=prompt,
            )
            # Check completeness and citations independently of model judgments.
            identifiers = [finding.requirement_id for finding in assessment.findings]
            if len(identifiers) != len(units) or set(identifiers) != set(units):
                return report(
                    "Requirements blocked: analysis must assess every requirement exactly once."
                )
            source_map = {s.id: s.content for s in sources}
            for finding in assessment.findings:
                if finding.status in {"aligned", "conflict"} and not finding.evidence:
                    return report(
                        "Requirements blocked: analysis lacks verifiable business evidence."
                    )
                for evidence in finding.evidence:
                    if evidence.source_id not in source_map or " ".join(
                        evidence.quote.split()
                    ) not in " ".join(source_map[evidence.source_id].split()):
                        return report(
                            "Requirements blocked: a source citation could not be verified."
                        )
            # Reject approval if the baseline changed while analysis was in flight.
            if path.read_bytes() != raw:
                return report(
                    "Requirements blocked: the baseline changed during analysis. Validate again."
                )
            result = report(
                "Requirements blocked: resolve the business-alignment findings before continuing.",
                assessment.findings,
            )
            if all(f.status == "aligned" for f in assessment.findings):
                result.status = "aligned"
                result.message = (
                    "Requirements align with the approved business sources. "
                    "Regulatory compliance is not assessed."
                )
            return result
        except Exception:
            # Never permit provider, configuration or parsing failures to become an approval.
            return report(
                "Requirements blocked: validation could not be completed. "
                "Check the business baseline and provider availability, then retry."
            )

    async def require(self, request: GenerateRequest) -> RequirementsReport:
        report = await self.assess(request)
        publish_lifecycle_event(
            "Requirements Validation Agent",
            "business_alignment",
            "success" if report.status == "aligned" else "failed",
            report.message,
        )
        if report.status != "aligned":
            raise RequirementsBlocked(report)
        return report
