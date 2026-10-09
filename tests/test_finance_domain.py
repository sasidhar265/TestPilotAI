"""Domain policy and arithmetic unit checks; API scenarios live in the ReqnRoll pack."""

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.finance_calculations import Annuity, Principal, Vat, calculate
from app.finance_domain import DomainPack, ground_request, load_domain_pack
from app.models import BusinessRule, GenerateRequest

PACK = Path(__file__).parents[1] / "workspace/auto-finance-domain.toml"


def pack():
    return load_domain_pack(PACK)


def governed():
    value = pack().model_dump()
    value["rules"] = [
        {
            "id": "BR-TEST",
            "description": "Synthetic test rule supplied by the test owner.",
            "version": "1",
            "owner": "Test owner",
            "source": "Unit test fixture",
            "status": "approved",
            "product_ids": ["HP"],
            "journey_ids": ["quotation"],
        },
        {
            "id": "BR-DRAFT",
            "description": "Draft rule must never govern generation.",
            "version": "1",
            "owner": "Test owner",
            "source": "Unit test fixture",
            "status": "draft",
        },
    ]
    return DomainPack.model_validate(value)


def test_only_explicit_scope_and_approved_rules_ground_requests():
    request = GenerateRequest(description="Validate supplied quotation rules")
    assert ground_request(request, governed()) == request
    request = request.model_copy(
        update={"finance_product_id": "HP", "finance_journey_ids": ["quotation"]}
    )
    enriched = ground_request(request, governed())
    assert [rule.id for rule in enriched.business_rules] == ["BR-TEST"]
    assert "reference-only" in enriched.additional_context
    assert ground_request(enriched, governed()) == enriched
    handoff = enriched.model_copy(
        update={
            "additional_context": enriched.additional_context
            + "\nREVIEWED STORY HANDOFF\nKeep this accepted story evidence."
        }
    )
    assert (
        "Keep this accepted story evidence."
        in ground_request(handoff, governed()).additional_context
    )
    unrelated = request.model_copy(update={"finance_product_id": "PCP"})
    assert ground_request(unrelated, governed()).business_rules == []
    with pytest.raises(ValueError, match="conflicts"):
        ground_request(
            request.model_copy(
                update={
                    "business_rules": [
                        BusinessRule(id="BR-TEST", description="Conflicting wording")
                    ]
                }
            ),
            governed(),
        )
    with pytest.raises(ValueError, match="Unknown"):
        ground_request(request.model_copy(update={"finance_product_id": "unknown"}), governed())


def test_domain_pack_rejects_ambiguous_or_unknown_references():
    value = pack().model_dump()
    value["products"].append(value["products"][0])
    with pytest.raises(ValidationError, match="unique"):
        DomainPack.model_validate(value)
    value = pack().model_dump()
    value["mappings"] = [
        {
            "project": "A",
            "requirement_key": "REQ-1",
            "requirement_version": 1,
            "product_id": "unknown",
        }
    ]
    with pytest.raises(ValidationError, match="unknown"):
        DomainPack.model_validate(value)


@pytest.mark.parametrize("balloon,regular", [("0", "1000.00"), ("6000", "500.00")])
def test_zero_interest_and_balloon_reconcile_exactly(balloon, regular):
    result = calculate(
        Annuity(
            kind="annuity",
            principal="12000",
            annual_nominal_rate="0",
            payments=12,
            balloon=balloon,
            deposit="1000",
            upfront_fees="100",
        ),
        pack(),
    )
    assert result["result"]["regular_payment"] == regular
    assert result["result"]["total_repayments"] == "12000.00"
    assert result["result"]["customer_total_payable"] == "13100.00"


def test_positive_interest_matches_independent_one_period_cashflow():
    result = calculate(
        Annuity(
            kind="annuity", principal="1000", annual_nominal_rate="12", payments=1, balloon="200"
        ),
        pack(),
    )["result"]
    assert result["regular_payment"] == "810.00"
    assert result["total_interest"] == "10.00"
    assert Decimal(result["total_repayments"]) == Decimal("1000") + Decimal(
        result["total_interest"]
    )


def test_rounding_adjusts_last_instalment_and_observed_mismatch_is_reported():
    result = calculate(
        Annuity(
            kind="annuity",
            principal="1",
            annual_nominal_rate="0",
            payments=3,
            observed={"regular_payment": "0.34"},
        ),
        pack(),
    )
    assert result["result"]["regular_payment"] == "0.33"
    assert result["result"]["final_regular_payment"] == "0.34"
    assert result["result"]["total_repayments"] == "1.00"
    assert result["matches_observed"] is False
    assert result["checks"][0]["difference"] == "0.01"


def test_vat_rounding_uses_configured_convention():
    original = pack()
    half_even = original.model_copy(update={"rounding": "half_even"})
    payload = Vat(kind="vat", net="0.05", vat_rate="10")
    assert calculate(payload, original)["result"]["vat"] == "0.01"
    assert calculate(payload, half_even)["result"]["vat"] == "0.00"


def test_precision_and_unknown_observations_fail_instead_of_guessing():
    with pytest.raises(ValueError, match="precision"):
        calculate(Principal(kind="principal", cash_price="100.001", deposit="0"), pack())
    with pytest.raises(ValueError, match="Unsupported"):
        calculate(Vat(kind="vat", net="100", vat_rate="0", observed={"apr": "0"}), pack())
    with pytest.raises(ValidationError):
        Annuity(kind="annuity", principal="100", annual_nominal_rate="0", payments=0)


def test_explicit_calculation_is_recomputed_for_generation_context():
    request = GenerateRequest(
        description="Verify instalments using supplied arithmetic inputs",
        finance_calculation={
            "kind": "annuity",
            "principal": "12000",
            "annual_nominal_rate": "0",
            "payments": 12,
        },
    )
    enriched = ground_request(request, pack())
    assert '"regular_payment": "1000.00"' in enriched.additional_context
    assert '"reference_calculation"' in enriched.additional_context
    invalid = request.model_copy(
        update={
            "finance_calculation": request.finance_calculation | {"trusted_expected_payment": "1"}
        }
    )
    with pytest.raises(ValidationError):
        ground_request(invalid, pack())
