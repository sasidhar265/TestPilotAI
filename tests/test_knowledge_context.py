"""Context transparency checks; these do not execute generated API suites."""

import json

import pytest

from app.config import Settings
from app.knowledge_context import knowledge_context
from app.models import GenerateRequest


def settings(tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"sources": []}))
    return Settings(requirements_baseline_path=baseline)


def test_preview_identifies_exact_scoped_references_without_approval(tmp_path):
    result = knowledge_context(
        GenerateRequest(
            description="Create PCP quotation coverage",
            finance_product_id="PCP",
            finance_journey_ids=["quotation"],
        ),
        "stories",
        settings(tmp_path),
    )
    assert [p["id"] for p in result["domain"]["products"]] == ["PCP"]
    assert [j["id"] for j in result["domain"]["journeys"]] == ["quotation"]
    assert result["domain"]["approved_rules"] == []
    assert result["approved_sources"] == []
    assert result["limitations"]
    assert len(result["topics"]) == 15
    assert all(t["authority"] == "reference_only" for t in result["topics"])
    assert all(len(t["fingerprint"]) == 64 for t in result["topics"])
    product = next(t for t in result["topics"] if t["id"] == "auto-finance-products.md")
    assert "Product distinctions and approval questions" in [
        s["title"] for s in product["sections"]
    ]


def test_scenario_preview_discloses_indirect_library_delivery(tmp_path):
    request = GenerateRequest(description="Create quotation scenarios")
    result = knowledge_context(request, "scenarios", settings(tmp_path))
    assert "not directly supplied" in result["delivery"]
    assert not result["domain"]["selected"]
    assert result["domain"]["products"] == []
    assert result["domain"]["journeys"] == []
    assert "not evidence of model reasoning" in result["notice"]
    assert (
        result["fingerprint"]
        == knowledge_context(request, "scenarios", settings(tmp_path))["fingerprint"]
    )


def test_disabled_selected_pack_is_rejected(tmp_path):
    config = settings(tmp_path).model_copy(update={"auto_finance_domain_enabled": False})
    with pytest.raises(ValueError, match="disabled"):
        knowledge_context(
            GenerateRequest(description="Quotation requirements", finance_product_id="PCP"),
            "stories",
            config,
        )
