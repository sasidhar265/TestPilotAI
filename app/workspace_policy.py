"""Shared, reloadable project rules and generation standards."""

import json
import os
import tempfile
from pathlib import Path

from pydantic import TypeAdapter

from app.models import BusinessRule, GenerateRequest

WORKSPACE = Path(__file__).resolve().parent.parent / "workspace"


def standards(name: str) -> str:
    if name not in {"automation", "feature"}:
        raise ValueError("Unknown standards file")
    return (WORKSPACE / f"{name}-standards.md").read_text(encoding="utf-8")


def load_business_rules() -> list[BusinessRule]:
    path = WORKSPACE / "business-rules.json"
    if path.stat().st_size > 200_000:
        raise ValueError("Shared business rules exceed 200 KB")
    return validate_rules(json.loads(path.read_text(encoding="utf-8")))


def validate_rules(value: object) -> list[BusinessRule]:
    rules = TypeAdapter(list[BusinessRule]).validate_python(value)
    if len(rules) > 100 or len({r.id for r in rules}) != len(rules):
        raise ValueError("Business rules must have unique IDs and contain at most 100 rules")
    return rules


def save_business_rules(rules: list[BusinessRule]) -> None:
    validate_rules(rules)
    content = json.dumps([r.model_dump() for r in rules], indent=2) + "\n"
    if len(content.encode()) > 200_000:
        raise ValueError("Shared business rules exceed 200 KB")
    with tempfile.NamedTemporaryFile(mode="w", dir=WORKSPACE, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        os.replace(temporary, WORKSPACE / "business-rules.json")
    finally:
        temporary.unlink(missing_ok=True)


def apply_rules(request: GenerateRequest) -> GenerateRequest:
    rules = {rule.id: rule for rule in load_business_rules()}
    # Existing API clients may still supply request-specific rules. Never override shared rules.
    for rule in request.business_rules:
        if rule.id in rules and rules[rule.id] != rule:
            raise ValueError(f"Rule {rule.id} conflicts with the shared business rules")
        rules[rule.id] = rule
    return request.model_copy(update={"business_rules": validate_rules(list(rules.values()))})


def without_tags(value: str) -> str:
    """Remove Gherkin tag lines while preserving doc-string payloads."""
    lines = []
    delimiter = None
    for line in value.splitlines():
        stripped = line.strip()
        if stripped.startswith(('"""', "```")):
            token = stripped[:3]
            delimiter = None if delimiter == token else token if delimiter is None else delimiter
        if delimiter is not None or not stripped.startswith("@"):
            lines.append(line)
    return "\n".join(lines)
