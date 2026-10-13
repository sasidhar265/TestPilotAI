"""The BA uses visible guide content, excluding scripts and UI controls."""

from app.domain_knowledge import GUIDE_TOPICS, guide_knowledge_sources, scope_guide_sources
from app.models import GenerateRequest


def test_new_pcp_quote_excludes_unrelated_products_and_lifecycle():
    selected, scope = scope_guide_sources(
        GenerateRequest(description="Create a quote creation endpoint for a New vehicle and PCP."),
        guide_knowledge_sources(include_units=True),
    )
    assert scope["product"] == "PCP"
    assert scope["vehicle_condition"] == "new"
    assert scope["journeys"] == ["quotation"]
    assert [s["id"] for s in selected] == [
        "UK-AUTO-FINANCE:products",
        "UK-AUTO-FINANCE:journey",
        "UK-AUTO-FINANCE:costs",
    ]
    content = "\n".join(s["content"] for s in selected)
    assert "Personal Contract Purchase" in content
    assert "Hire Purchase" not in content
    assert "Business Contract Hire" not in content
    assert "MOT" not in content
    assert "negative equity" not in content
    assert "underwriting" in scope["excluded_journeys"]


def test_explicit_selectors_override_mentions_and_excluded_functions():
    selected, scope = scope_guide_sources(
        GenerateRequest(
            description="Create PCP quotes. Underwriting is out of scope.",
            finance_product_id="HP",
            finance_journey_ids=["quotation"],
        ),
        guide_knowledge_sources(include_units=True),
    )
    assert scope["product"] == "HP"
    assert scope["journeys"] == ["quotation"]
    assert "Personal Contract Purchase" not in selected[0]["content"]


def test_unclear_scope_does_not_require_entire_domain_catalogue():
    selected, scope = scope_guide_sources(
        GenerateRequest(description="Implement the requested endpoint."),
        guide_knowledge_sources(include_units=True),
    )
    assert selected == []
    assert scope["scope_status"] == "needs_clarification"


def test_guide_topics_preserve_products_journeys_sources_and_reference_authority():
    sources = guide_knowledge_sources()
    assert [s["id"] for s in sources] == [f"UK-AUTO-FINANCE:{topic}" for topic in GUIDE_TOPICS]
    products = next(s for s in sources if s["id"].endswith(":products"))
    assert "Personal Contract Purchase" in products["content"]
    assert "Business Contract Purchase" in products["content"]
    assert "Sale and Leaseback" in products["content"]
    assert "moneyhelper.org.uk" in products["reference_urls"]
    for source in sources:
        assert source["authority"] == "reference_only"
        assert len(source["fingerprint"]) == 64
        assert "selectNode" not in source["content"]
        assert "Download HTML" not in source["content"]
        assert "All customers" not in source["content"]
        assert "font-size" not in source["content"]
