"""Shared, reloadable project rules and generation standards."""

import os
import re
import tempfile
from pathlib import Path

from pydantic import TypeAdapter

from app.models import BusinessRule, GenerateRequest

WORKSPACE = Path(__file__).resolve().parent.parent / "workspace"
RULES_PATH = WORKSPACE.parent / ".github" / "agents" / "business-rules.agent.md"
RULES_START = "<!-- shared-business-rules:start -->"
RULES_END = "<!-- shared-business-rules:end -->"


def _rule_document() -> tuple[str, str, str]:
    if RULES_PATH.stat().st_size > 200_000:
        raise ValueError("Shared business rules exceed 200 KB")
    content = RULES_PATH.read_text(encoding="utf-8")
    if content.count(RULES_START) != 1 or content.count(RULES_END) != 1:
        raise ValueError("Business Rules Agent must contain one shared-business-rules section")
    before, body = content.split(RULES_START)
    if RULES_END not in body:
        raise ValueError("Shared business rule section markers are out of order")
    body, after = body.split(RULES_END)
    return before, body, after


def standards(name: str) -> str:
    if name not in {"automation", "feature"}:
        raise ValueError("Unknown standards file")
    return (WORKSPACE / f"{name}-standards.md").read_text(encoding="utf-8")


def load_business_rules() -> list[BusinessRule]:
    _, body, _ = _rule_document()
    entries: list[dict[str, str]] = []
    for line in body.strip("\n").splitlines():
        match = re.fullmatch(r"- (BR-[A-Za-z0-9_-]+): (.*)", line)
        if match:
            entries.append({"id": match[1], "description": match[2]})
        elif line.startswith("  ") and entries:
            entries[-1]["description"] += "\n" + line[2:]
        elif line.strip():
            raise ValueError("Shared rules must use '- BR-ID: description' Markdown bullets")
    return validate_rules(entries)


def validate_rules(value: object) -> list[BusinessRule]:
    rules = TypeAdapter(list[BusinessRule]).validate_python(value)
    if len(rules) > 100 or len({r.id for r in rules}) != len(rules):
        raise ValueError("Business rules must have unique IDs and contain at most 100 rules")
    return rules


def save_business_rules(rules: list[BusinessRule]) -> None:
    validate_rules(rules)
    before, _, after = _rule_document()
    bullets = []
    for rule in rules:
        description = rule.description.replace("\n", "\n  ")
        if RULES_START in description or RULES_END in description or "\r" in description:
            raise ValueError("Rule descriptions cannot contain section markers or carriage returns")
        bullets.append(f"- {rule.id}: {description}")
    content = before + RULES_START + "\n" + "\n".join(bullets) + "\n" + RULES_END + after
    if len(content.encode("utf-8")) > 200_000:
        raise ValueError("Shared business rules exceed 200 KB")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=RULES_PATH.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        os.replace(temporary, RULES_PATH)
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
