"""Bounded identities for the actual inputs and artifacts checked by agents."""

import hashlib

from pydantic import BaseModel

from app.models import GenerateRequest


def fingerprint(value: BaseModel) -> str:
    return hashlib.sha256(value.model_dump_json().encode()).hexdigest()[:12]


def labels(values: list[str]) -> str:
    selected = [" ".join(value.split())[:120] for value in values[:5]]
    suffix = f"; +{len(values) - 5} more" if len(values) > 5 else ""
    return "; ".join(selected) + suffix


def functionality(request: GenerateRequest) -> str:
    title = next((line.strip() for line in request.description.splitlines() if line.strip()), "")
    return f"Functionality: {title[:160]}. Request {fingerprint(request)}."
