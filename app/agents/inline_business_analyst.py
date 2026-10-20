"""Typed BA analysis through the existing provider and in-house knowledge pipeline."""

import hashlib
import json

from app.agent_instructions import load_agent_instructions
from app.agents.business_analyst import BusinessAnalystAgent
from app.agents.runner import StructuredAgentDefinition
from app.ba_review_models import BAReviewOutput
from app.business_delivery import validate_business_deliverables
from app.models import GenerateRequest


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def source_sections(document: str) -> list[dict]:
    """Stable extracted-line references; never pretend these are original page numbers."""
    sections = []
    offset = 0
    for number, line in enumerate(document.splitlines(keepends=True), 1):
        if line.strip():
            sections.append(
                dict(
                    id=f"L{number:04d}",
                    text=line.strip(),
                    start=offset,
                    end=offset + len(line),
                    page=None,
                )
            )
        offset += len(line)
    return sections


def validate_output(
    output: BAReviewOutput, sections: list[dict], sources: list[dict]
) -> BAReviewOutput:
    source_map = {source["id"]: source["content"] for source in sources}
    section_map = {section["id"]: section["text"] for section in sections}
    validate_business_deliverables(output.business_deliverables, "\n".join(section_map.values()))
    requirements = {item.requirement_id for item in output.requirements}
    findings = {item.finding_id for item in output.findings}
    if len(requirements) != len(output.requirements) or len(findings) != len(output.findings):
        raise ValueError("Requirement and finding identifiers must be unique")
    if len({q.question_id for q in output.business_questions}) != len(output.business_questions):
        raise ValueError("Question identifiers must be unique")

    def reference(ref):
        text = (
            section_map.get(ref.section_id)
            if ref.source_id == "BRD"
            else source_map.get(ref.source_id)
        )
        if not text or " ".join(ref.quote.split()) not in " ".join(text.split()):
            raise ValueError("Source quotation or extracted section could not be verified")
        if ref.source_id != "BRD" and ref.section_id is not None:
            raise ValueError("Do not invent section identifiers for knowledge sources")

    for item in output.requirements:
        if not any(ref.source_id == "BRD" for ref in item.source_references):
            raise ValueError("Every requirement needs an original BRD reference")
        for ref in item.source_references:
            reference(ref)
    for item in output.findings:
        if not set(item.requirement_ids) <= requirements:
            raise ValueError("Finding references an unknown requirement")
        if not any(ref.source_id == "BRD" for ref in item.evidence_references):
            raise ValueError("Every finding needs a BRD anchor")
        if item.finding_type in {"CONFLICT", "DUPLICATE"} and len(item.evidence_references) < 2:
            raise ValueError("Conflicts and duplicates require both source references")
        if (
            item.finding_type in {"CONFLICT", "DUPLICATE"}
            and len(
                {(ref.source_id, ref.section_id, ref.quote) for ref in item.evidence_references}
            )
            < 2
        ):
            raise ValueError("Conflicts and duplicates require distinct source evidence")
        for ref in item.evidence_references:
            reference(ref)
    for dependency in output.dependencies:
        if dependency.source_requirement_id not in requirements:
            raise ValueError("Dependency references an unknown requirement")
        if (
            dependency.confirmation_status == "SOURCE_SUPPORTED"
            and not dependency.evidence_references
        ):
            raise ValueError("Confirmed dependencies need evidence")
        for ref in dependency.evidence_references:
            reference(ref)
    for question in output.business_questions:
        if not set(question.linked_finding_ids) <= findings:
            raise ValueError("Question references an unknown finding")
    for calculation in output.calculations:
        if calculation.requirement_id not in requirements:
            raise ValueError("Calculation references an unknown requirement")
        for ref in calculation.evidence_references:
            reference(ref)
        if calculation.approved_method and not any(
            ref.source_id in source_map
            and next(source for source in sources if source["id"] == ref.source_id)["authority"]
            == "approved_business_source"
            for ref in calculation.evidence_references
        ):
            raise ValueError("An approved calculation method needs approved-source evidence")
    # Readiness is conservative even if the model contradicts its own findings.
    if any(item.readiness == "BLOCKED" for item in output.requirements) or any(
        f.severity == "BLOCKER"
        or f.severity == "HIGH"
        and f.finding_type
        in {"CALCULATION_GAP", "COMPLIANCE_REVIEW_REQUIRED", "INTEGRATION_DEPENDENCY"}
        for f in output.findings
    ):
        output.readiness_status = "BLOCKED"
    elif (
        output.findings
        or any(q.blocking_status for q in output.business_questions)
        or any(item.readiness == "NEEDS_CLARIFICATION" for item in output.requirements)
    ):
        if output.readiness_status == "READY_FOR_BA_REVIEW":
            output.readiness_status = "NEEDS_CLARIFICATION"
    return output


def stable_output(output: BAReviewOutput) -> dict:
    data = output.model_dump(mode="json")
    requirement_ids, finding_ids = {}, {}
    for item in data["requirements"]:
        key = fingerprint(
            [
                item["category"],
                item["source_references"],
                " ".join(item["title"].casefold().split()),
            ]
        )[:16]
        new_id = f"REQ-{key}"
        requirement_ids[item["requirement_id"]] = new_id
        item["requirement_id"] = new_id
    for item in data["findings"]:
        item["requirement_ids"] = [requirement_ids[key] for key in item["requirement_ids"]]
        key = fingerprint(
            [
                item["finding_type"],
                item["requirement_ids"],
                item["evidence_references"],
                item["clarification_question"],
            ]
        )[:16]
        new_id = f"FND-{key}"
        finding_ids[item["finding_id"]] = new_id
        item["finding_id"] = new_id
        item["proposal_fingerprint"] = fingerprint(item)
        item["version"] = 1
    for question in data["business_questions"]:
        question["linked_finding_ids"] = [
            finding_ids[key] for key in question["linked_finding_ids"]
        ]
        question["question_id"] = "Q-" + fingerprint(question["question"])[:16]
    for dependency in data["dependencies"]:
        dependency["source_requirement_id"] = requirement_ids[dependency["source_requirement_id"]]
    for calculation in data["calculations"]:
        calculation["requirement_id"] = requirement_ids[calculation["requirement_id"]]
    if len({r["requirement_id"] for r in data["requirements"]}) != len(data["requirements"]):
        raise ValueError("Duplicate extracted requirements; combine identical source anchors")
    if len({f["finding_id"] for f in data["findings"]}) != len(data["findings"]):
        raise ValueError("Duplicate findings must be consolidated")
    return data


class InlineBusinessAnalyst(BusinessAnalystAgent):
    async def analyse(
        self,
        request: GenerateRequest,
        sections: list[dict],
        sources: list[dict],
        limitations: list[str],
        focus: str | None = None,
    ) -> dict:
        prompt = json.dumps(
            dict(
                brd_source_id="BRD",
                brd_reference_format={
                    "source_id": "BRD",
                    "section_id": "L0001",
                    "quote": "Exact text from the corresponding source section",
                },
                source_sections=sections,
                knowledge_sources=sources,
                knowledge_limitations=limitations,
                source_context=request.additional_context,
                configured_product=request.finance_product_id,
                configured_journeys=request.finance_journey_ids,
                candidate_calculation_context=request.finance_calculation,
                candidate_rules=[rule.model_dump() for rule in request.business_rules],
                focus_requirement=focus,
                coverage="Return the complete baseline, including exclusions and implied rules.",
            ),
            ensure_ascii=False,
        )

        def validate(output):
            validate_output(output, sections, sources)
            stable_output(output)
            return output

        result = await self.runner.generate_structured(
            StructuredAgentDefinition(
                BAReviewOutput,
                "BA analysis timed out.",
                "No BA analysis returned.",
                "Invalid BA analysis returned.",
            ),
            instructions=load_agent_instructions("ba-inline-review"),
            prompt=prompt,
            validate=validate,
            llm_model=request.llm_model,
        )
        validate(result)
        data = stable_output(result)
        data["analysis_limitations"] = list(
            dict.fromkeys([*data["analysis_limitations"], *limitations])
        )
        return data
