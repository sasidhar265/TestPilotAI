"""Explicit auto-finance catalogue and approved-rule grounding; no inferred policy."""

import json
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import BusinessRule, GenerateRequest


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CatalogueItem(DomainModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,49}$")
    name: str = Field(min_length=1, max_length=200)
    focus: list[str] = Field(default_factory=list, max_length=20)


class DomainRule(DomainModel):
    id: str = Field(pattern=r"^BR-[A-Za-z0-9_-]+$")
    description: str = Field(min_length=1, max_length=2000)
    status: Literal["draft", "approved"] = "draft"
    version: str = Field(min_length=1, max_length=100)
    owner: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=1000)
    product_ids: list[str] = Field(default_factory=list)
    journey_ids: list[str] = Field(default_factory=list)


class DomainMapping(DomainModel):
    project: str = Field(min_length=1, max_length=100)
    requirement_key: str = Field(min_length=1, max_length=100)
    requirement_version: int = Field(ge=1)
    product_id: str
    journey_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)


class DomainPack(DomainModel):
    version: str = Field(min_length=1, max_length=100)
    market: str = Field(min_length=1, max_length=100)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    minor_units: int = Field(default=2, ge=0, le=4)
    rounding: Literal["half_up", "half_even"] = "half_up"
    products: list[CatalogueItem] = Field(max_length=100)
    journeys: list[CatalogueItem] = Field(max_length=100)
    rules: list[DomainRule] = Field(default_factory=list, max_length=100)
    mappings: list[DomainMapping] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def consistent_references(self) -> "DomainPack":
        for items in (self.products, self.journeys, self.rules):
            if len({item.id for item in items}) != len(items):
                raise ValueError("Domain catalogue identifiers must be unique")
        products = {item.id for item in self.products}
        journeys = {item.id for item in self.journeys}
        rules = {item.id for item in self.rules}
        for rule in self.rules:
            if set(rule.product_ids) - products or set(rule.journey_ids) - journeys:
                raise ValueError("Domain rule references an unknown product or journey")
        keys = set()
        for mapping in self.mappings:
            key = (mapping.project, mapping.requirement_key, mapping.requirement_version)
            if key in keys:
                raise ValueError("Each project requirement must have one domain mapping")
            keys.add(key)
            if (
                mapping.product_id not in products
                or set(mapping.journey_ids) - journeys
                or set(mapping.rule_ids) - rules
            ):
                raise ValueError("Domain mapping contains an unknown reference")
        return self


def load_domain_pack(path: Path) -> DomainPack:
    if path.stat().st_size > 200_000:
        raise ValueError("Auto-finance domain pack exceeds 200 KB")
    return DomainPack.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))


def ground_request(request: GenerateRequest, pack: DomainPack) -> GenerateRequest:
    """Only explicitly selected scopes contribute reference context and approved rules."""
    if (
        not request.finance_product_id
        and not request.finance_journey_ids
        and request.finance_calculation is None
    ):
        return request
    calculation = None
    if request.finance_calculation is not None:
        from pydantic import TypeAdapter

        from app.finance_calculations import CalculationInput, calculate

        calculation = calculate(
            TypeAdapter(CalculationInput).validate_python(request.finance_calculation), pack
        )
    products = [item for item in pack.products if item.id == request.finance_product_id]
    journeys = [item for item in pack.journeys if item.id in request.finance_journey_ids]
    if (request.finance_product_id and not products) or len(journeys) != len(
        set(request.finance_journey_ids)
    ):
        raise ValueError("Unknown auto-finance product or journey")
    rules = {rule.id: rule for rule in request.business_rules}
    selected = []
    for rule in pack.rules:
        product_matches = not rule.product_ids or request.finance_product_id in rule.product_ids
        journey_matches = not rule.journey_ids or bool(
            set(rule.journey_ids) & set(request.finance_journey_ids)
        )
        if rule.status == "approved" and product_matches and journey_matches:
            approved = BusinessRule(id=rule.id, description=rule.description)
            if rule.id in rules and rules[rule.id] != approved:
                raise ValueError(f"Rule {rule.id} conflicts with the approved domain pack")
            rules[rule.id] = approved
            selected.append(rule.model_dump())
    context = "AUTO-FINANCE DOMAIN PACK\n" + json.dumps(
        {
            "version": pack.version,
            "market": pack.market,
            "currency": pack.currency,
            "reference_products": [item.model_dump() for item in products],
            "reference_journeys": [item.model_dump() for item in journeys],
            "approved_rules": selected,
            "reference_calculation": calculation,
            "guidance": (
                "Catalogue focus is reference-only, not approval. Do not infer limits, "
                "eligibility, pricing, APR, settlement methods or API fields. Obtain missing "
                "rules from the owner. Mathematical calculators apply only to declared conventions."
            ),
        },
        sort_keys=True,
    )
    start = "\n\nAUTO-FINANCE DOMAIN PACK\n"
    end = "\nEND AUTO-FINANCE DOMAIN PACK\n"
    base = request.additional_context
    if start in base:
        before, _, previous = base.partition(start)
        _, separator, after = previous.partition(end)
        if not separator or start in after:
            raise ValueError("Malformed auto-finance domain context")
        base = before + after
    return GenerateRequest.model_validate(
        request.model_dump()
        | {
            "business_rules": list(rules.values()),
            "additional_context": base + "\n\n" + context + end,
        }
    )
