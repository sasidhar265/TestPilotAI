"""Decimal reference calculations with declared conventions and observed-value validation."""

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.finance_domain import DomainModel, DomainPack

Money = Annotated[Decimal, Field(ge=0, le=Decimal("1000000000"), max_digits=18, decimal_places=8)]
Rate = Annotated[Decimal, Field(ge=0, le=100, decimal_places=8)]


class Calculation(DomainModel):
    observed: dict[str, Money] = Field(default_factory=dict, max_length=20)


class Annuity(Calculation):
    kind: Literal["annuity"]
    principal: Money
    annual_nominal_rate: Rate
    payments: int = Field(ge=1, le=600)
    balloon: Money = Decimal(0)
    upfront_fees: Money = Decimal(0)
    deposit: Money = Decimal(0)

    @model_validator(mode="after")
    def valid_balloon(self) -> "Annuity":
        if self.principal <= 0 or self.balloon > self.principal:
            raise ValueError("Principal must be positive and balloon cannot exceed principal")
        return self


class Principal(Calculation):
    kind: Literal["principal"]
    cash_price: Money
    deposit: Money
    financed_fees: Money = Decimal(0)

    @model_validator(mode="after")
    def valid_deposit(self) -> "Principal":
        if self.deposit > self.cash_price:
            raise ValueError("Deposit cannot exceed cash price")
        return self


class Vat(Calculation):
    kind: Literal["vat"]
    net: Money
    vat_rate: Rate


CalculationInput = Annotated[Annuity | Principal | Vat, Field(discriminator="kind")]


def calculate(payload: Annuity | Principal | Vat, pack: DomainPack) -> dict[str, object]:
    rounding = ROUND_HALF_UP if pack.rounding == "half_up" else ROUND_HALF_EVEN
    quantum = Decimal(1).scaleb(-pack.minor_units)

    def money(value: Decimal) -> Decimal:
        return value.quantize(quantum, rounding=rounding)

    monetary_fields = {
        "principal",
        "balloon",
        "deposit",
        "upfront_fees",
        "cash_price",
        "financed_fees",
        "net",
    }
    for key, value in payload.model_dump().items():
        if key in monetary_fields and value != money(value):
            raise ValueError(f"{key} exceeds the configured currency precision")
    with localcontext() as context:
        context.prec = 50
        if isinstance(payload, Principal):
            result = {
                "amount_financed": money(
                    payload.cash_price - payload.deposit + payload.financed_fees
                )
            }
            convention = "cash price minus deposit plus explicitly financed fees"
        elif isinstance(payload, Vat):
            vat = money(payload.net * payload.vat_rate / 100)
            result = {
                "net": money(payload.net),
                "vat": vat,
                "gross": money(money(payload.net) + vat),
            }
            convention = "supplied VAT rate applied to net amount; no tax rate is inferred"
        else:
            rate = payload.annual_nominal_rate / 1200
            factor = (1 + rate) ** payload.payments
            payment = (
                (payload.principal - payload.balloon) / payload.payments
                if rate == 0
                else (payload.principal * factor - payload.balloon) * rate / (factor - 1)
            )
            regular = money(payment)
            balance = payload.principal
            interest_total = Decimal(0)
            final = regular
            for period in range(1, payload.payments + 1):
                interest = money(balance * rate)
                interest_total += interest
                final = (
                    money(balance + interest - payload.balloon)
                    if period == payload.payments
                    else regular
                )
                if final < 0:
                    raise ValueError(
                        "Rounding produces a negative final payment; "
                        "increase precision or revise the inputs"
                    )
                balance = money(balance + interest - final)
            repayments = money(regular * (payload.payments - 1) + final + payload.balloon)
            result = {
                "regular_payment": regular,
                "final_regular_payment": final,
                "balloon": money(payload.balloon),
                "total_interest": money(interest_total),
                "total_repayments": repayments,
                "customer_total_payable": money(
                    repayments + payload.deposit + payload.upfront_fees
                ),
            }
            convention = (
                "fixed nominal annual rate / 12; monthly payments in arrears; "
                "interest rounded each period; balloon paid with last regular payment; "
                "last regular payment adjusted for rounding"
            )
        unknown = set(payload.observed) - result.keys()
        if unknown:
            raise ValueError(
                "Unsupported observed calculation fields: " + ", ".join(sorted(unknown))
            )
        checks = [
            {
                "field": key,
                "expected": str(result[key]),
                "observed": str(value),
                "difference": str(value - result[key]),
                "passed": value == result[key],
            }
            for key, value in payload.observed.items()
        ]
        return {
            "kind": payload.kind,
            "currency": pack.currency,
            "rounding": pack.rounding,
            "minor_units": pack.minor_units,
            "convention": convention,
            "result": {key: str(value) for key, value in result.items()},
            "checks": checks,
            "matches_observed": all(check["passed"] for check in checks) if checks else None,
            "scope": (
                "Reference arithmetic only. Not an approved product pricing engine, "
                "statutory APR or early-settlement calculation."
            ),
        }
