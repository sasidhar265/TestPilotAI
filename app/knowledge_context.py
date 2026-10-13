"""Inspectable generation context; reference exposure is not model attribution."""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

from app.agent_instructions import profile_knowledge_sources
from app.agents.business_analyst import BusinessAnalystAgent
from app.config import Settings
from app.finance_domain import ground_request, load_domain_pack
from app.models import GenerateRequest
from app.workspace_policy import load_business_rules

KnowledgeStage = Literal["ba-review", "validate-requirements", "stories", "scenarios", "test-cases"]


class KnowledgePreviewRequest(BaseModel):
    stage: KnowledgeStage
    request: GenerateRequest


def knowledge_context(request: GenerateRequest, stage: KnowledgeStage, settings: Settings) -> dict:
    sources, _, limitations = BusinessAnalystAgent(settings).knowledge()
    topics = []
    for source in profile_knowledge_sources(settings.agent_profile):
        content = source["content"]
        sections = []
        for part in re.split(r"(?m)^## ", content)[1:]:
            title, _, body = part.partition("\n")
            sections.append({"title": title.strip(), "points": body.strip()})
        version = re.search(r"(?m)^Version: (.+)$", content)
        topics.append(
            {
                "id": source["id"],
                "title": source["title"],
                "path": source["path"],
                "authority": "reference_only",
                "version": version[1] if version else "workspace",
                "fingerprint": hashlib.sha256(content.encode()).hexdigest(),
                "sections": sections,
            }
        )
    selected = bool(
        request.finance_product_id
        or request.finance_journey_ids
        or request.finance_calculation is not None
    )
    domain = {
        "enabled": settings.auto_finance_domain_enabled,
        "selected": selected,
        "path": str(settings.auto_finance_domain_path),
        "products": [],
        "journeys": [],
        "approved_rules": [],
        "calculation": None,
    }
    if settings.auto_finance_domain_enabled:
        pack = load_domain_pack(settings.auto_finance_domain_path)
        domain.update(
            {
                "version": pack.version,
                "market": pack.market,
                "currency": pack.currency,
                "minor_units": pack.minor_units,
                "rounding": pack.rounding,
            }
        )
        if selected:
            grounded = ground_request(request, pack)
            shared = {r.id: r for r in load_business_rules()}
            for rule in grounded.business_rules:
                if rule.id in shared and shared[rule.id] != rule:
                    raise ValueError(f"Rule {rule.id} conflicts with the shared business rules")
            payload = json.loads(
                grounded.additional_context.split("AUTO-FINANCE DOMAIN PACK\n", 1)[1].split(
                    "\nEND AUTO-FINANCE DOMAIN PACK", 1
                )[0]
            )
            domain.update(
                {
                    "products": payload["reference_products"],
                    "journeys": payload["reference_journeys"],
                    "approved_rules": payload["approved_rules"],
                    "calculation": payload["reference_calculation"],
                }
            )
    elif selected:
        raise ValueError("Auto-finance domain pack is disabled")
    inputs = {
        "ba-review": "Profile library and business sources are supplied directly to BA review.",
        "validate-requirements": (
            "Effective approved baseline sources govern alignment. The profile is reference "
            "context when AI alignment runs. A verified uploaded BRD can satisfy the source "
            "gate without AI alignment."
        ),
        "stories": (
            "Profile knowledge and business sources are supplied directly alongside the "
            "requirements. Story source excerpts and IDs are validated."
        ),
        "scenarios": (
            "The scenario generator receives reviewed stories, request context and "
            "applicable rules. The full profile library is not directly supplied to "
            "scenario generation; it informs upstream stories and the alignment gate."
        ),
        "test-cases": (
            "The profile library, reviewed story/scenario handoff and governing request "
            "rules guide specialist generation. The Quality Gate checks generated cases."
        ),
    }
    result = {
        "stage": stage,
        "request_fingerprint": hashlib.sha256(request.model_dump_json().encode()).hexdigest(),
        "profile": settings.agent_profile,
        "prepared_at": datetime.now(UTC).isoformat(),
        "delivery": inputs[stage],
        "topics": topics,
        "domain": domain,
        "approved_sources": [s for s in sources if s["authority"] == "approved_business_source"],
        "shared_rules": [r.model_dump() for r in load_business_rules()],
        "request_rules": [r.model_dump() for r in request.business_rules],
        "uploaded_brd_present": bool(request.uploaded_brd_receipt),
        "limitations": limitations,
        "notice": (
            "This is a snapshot of available context before the operation, not evidence of "
            "model reasoning or a claim that every topic applies. Current explicit "
            "requirements and approved contracts take precedence. Configuration can change "
            "after this preview; generated evidence and validation results must be reviewed "
            "separately."
        ),
    }
    result["fingerprint"] = hashlib.sha256(
        json.dumps({k: v for k, v in result.items() if k != "prepared_at"}, sort_keys=True).encode()
    ).hexdigest()
    return result
