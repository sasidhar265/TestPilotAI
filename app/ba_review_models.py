"""Versioned, source-grounded BA proposals. Approval metadata is always server-owned."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.business_delivery import BusinessDeliverable


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceReference(ReviewModel):
    source_id: str = Field(min_length=1, max_length=200)
    section_id: str | None = None
    quote: str = Field(min_length=5, max_length=3000)


Readiness = Literal["BLOCKED", "NEEDS_CLARIFICATION", "READY_FOR_BA_REVIEW"]
FindingType = Literal[
    "AMBIGUITY",
    "MISSING_REQUIREMENT",
    "CONFLICT",
    "DUPLICATE",
    "INCOMPLETE_BUSINESS_RULE",
    "CALCULATION_GAP",
    "DATA_GAP",
    "INTEGRATION_DEPENDENCY",
    "NON_FUNCTIONAL_GAP",
    "COMPLIANCE_REVIEW_REQUIRED",
    "TESTABILITY_GAP",
    "UNSUPPORTED_ASSUMPTION",
]


class RequirementProposal(ReviewModel):
    requirement_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=5, max_length=6000)
    category: Literal["FUNCTIONAL", "NON_FUNCTIONAL", "BUSINESS_RULE", "EXCLUSION", "IMPLIED"]
    product_scope: list[str] = Field(max_length=30)
    source_references: list[SourceReference] = Field(min_length=1, max_length=30)
    acceptance_criteria_drafts: list[str] = Field(max_length=30)
    dependencies: list[str] = Field(max_length=30)
    readiness: Readiness


class FindingProposal(ReviewModel):
    finding_id: str = Field(min_length=1, max_length=100)
    requirement_ids: list[str] = Field(min_length=1, max_length=30)
    finding_type: FindingType
    severity: Literal["BLOCKER", "HIGH", "MEDIUM", "LOW"]
    title: str = Field(min_length=3, max_length=300)
    detailed_explanation: str = Field(min_length=10, max_length=6000)
    business_impact: str = Field(min_length=10, max_length=3000)
    evidence_references: list[SourceReference] = Field(min_length=1, max_length=30)
    missing_information: list[str] = Field(max_length=30)
    clarification_question: str = Field(min_length=10, max_length=3000)
    recommended_action: str = Field(min_length=10, max_length=3000)
    suggested_requirement_text: str | None = Field(default=None, max_length=6000)
    proposed_acceptance_criteria: list[str] = Field(max_length=30)
    suggested_stakeholder: str | None = Field(default=None, max_length=200)
    evidence_confidence: Literal["SOURCE_SUPPORTED", "INFERRED_REQUIRES_VALIDATION", "UNKNOWN"]
    review_status: Literal["PENDING"] = "PENDING"


class DependencyProposal(ReviewModel):
    source_requirement_id: str
    target_artifact_or_system: str = Field(min_length=1, max_length=300)
    relationship: Literal[
        "REQUIRES", "BLOCKS", "RELATES_TO", "CONFLICTS_WITH", "DUPLICATES", "IMPACTS"
    ]
    rationale: str = Field(min_length=10, max_length=3000)
    evidence_references: list[SourceReference] = Field(max_length=30)
    confirmation_status: Literal["SOURCE_SUPPORTED", "SUGGESTED_REQUIRES_VALIDATION"]


class BusinessQuestion(ReviewModel):
    question_id: str
    linked_finding_ids: list[str] = Field(max_length=30)
    question: str = Field(min_length=10, max_length=3000)
    suggested_owner: str | None
    blocking_status: bool


class CalculationReview(ReviewModel):
    requirement_id: str
    inputs: list[str]
    approved_method: str | None
    calculation_order: list[str]
    rounding_and_precision: str | None
    product_types: list[str]
    outputs: list[str]
    boundaries: list[str]
    missing_decisions: list[str]
    dependencies: list[str]
    test_scenarios: list[str]
    evidence_references: list[SourceReference]


class BAReviewOutput(ReviewModel):
    schema_version: Literal["1.0"]
    readiness_status: Readiness
    summary: str = Field(min_length=20, max_length=6000)
    scope: list[str] = Field(max_length=50)
    business_deliverables: list[BusinessDeliverable] = Field(default_factory=list, max_length=50)
    analysis_limitations: list[str] = Field(max_length=50)
    requirements: list[RequirementProposal] = Field(min_length=1, max_length=150)
    findings: list[FindingProposal] = Field(max_length=150)
    dependencies: list[DependencyProposal] = Field(max_length=150)
    business_questions: list[BusinessQuestion] = Field(max_length=150)
    calculations: list[CalculationReview] = Field(max_length=100)


class ReviewStart(ReviewModel):
    baseline: int = Field(ge=1)
    force: bool = False
    requirement_id: str | None = Field(default=None, max_length=100)


class FindingDecision(ReviewModel):
    revision: int = Field(ge=1)
    finding_id: str = Field(min_length=1, max_length=100)
    finding_version: int = Field(ge=1)
    action: Literal["accept", "edit", "reject", "clarify", "comment", "resolve"]
    comment: str = Field(min_length=1, max_length=4000, pattern=r"\S")
    proposed_text: str | None = Field(default=None, max_length=6000)


class ReviewSignoff(ReviewModel):
    revision: int = Field(ge=1)
    comment: str = Field(min_length=1, max_length=4000, pattern=r"\S")


class BRDRevisionRequest(ReviewModel):
    revision: int = Field(ge=1)
