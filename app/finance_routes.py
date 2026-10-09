"""Owner-configured domain references and deterministic calculation tools."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.finance_calculations import CalculationInput, calculate
from app.finance_domain import DomainPack, load_domain_pack

router = APIRouter(prefix="/api/finance", tags=["Auto finance"])
logger = logging.getLogger(__name__)


def domain(settings: Annotated[Settings, Depends(get_settings)]) -> DomainPack:
    if not settings.auto_finance_domain_enabled:
        raise HTTPException(503, "Auto-finance domain pack is disabled")
    try:
        return load_domain_pack(settings.auto_finance_domain_path)
    except (OSError, ValueError):
        logger.error("finance_domain_configuration_invalid")
        raise HTTPException(
            503, "Auto-finance domain configuration is invalid; check the domain pack"
        ) from None


Pack = Annotated[DomainPack, Depends(domain)]


@router.get("/domain-pack")
def catalogue(pack: Pack) -> dict[str, object]:
    return pack.model_dump() | {"reference_only": True}


@router.post("/calculations")
def calculation(payload: CalculationInput, pack: Pack) -> dict[str, object]:
    try:
        result = calculate(payload, pack)
    except (ValueError, ArithmeticError) as error:
        raise HTTPException(422, str(error)) from None
    logger.info(
        "finance_calculation_complete kind=%s observed_fields=%s",
        payload.kind,
        len(payload.observed),
        extra={
            "event_details": {"kind": payload.kind, "observed_fields": str(len(payload.observed))}
        },
    )
    return result
