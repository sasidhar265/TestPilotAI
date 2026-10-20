"""BRD-grounded delivery expectations and expected business benefits."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BusinessDeliverable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectation: str = Field(min_length=5, max_length=2000)
    deliverable: str = Field(min_length=5, max_length=2000)
    business_benefit: str = Field(min_length=5, max_length=2000)
    delivery_impact: str = Field(min_length=5, max_length=2000)
    benefit_basis: Literal["stated_in_brd", "inferred_requires_confirmation"]
    success_measure: str | None = Field(default=None, max_length=2000)
    document_quote: str = Field(min_length=5, max_length=2000)


def validate_business_deliverables(items: list[BusinessDeliverable], document: str) -> None:
    source = " ".join(document.split())
    for item in items:
        if " ".join(item.document_quote.split()) not in source:
            raise ValueError("A business deliverable BRD quotation could not be verified.")
