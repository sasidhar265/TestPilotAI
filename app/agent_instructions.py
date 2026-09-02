"""Load repository-owned Markdown agent policies for the governed runtime."""

import re
from functools import lru_cache
from pathlib import Path

AGENT_DIRECTORY = Path(__file__).parent.parent / ".github" / "agents"
PROFILE_DIRECTORY = Path(__file__).parent.parent / ".github" / "agent-profiles"
_PROFILE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
AGENT_FILES = {
    "business-rules": "business-rules.agent.md",
    "reqforge": "reqforge.agent.md",
    "testpilot-coordinator": "testpilot-coordinator.agent.md",
    "manual-test-generator": "manual-test-generator.agent.md",
    "manual-testing-specialist": "manual-testing-specialist.agent.md",
    "automation-test-generator": "automation-test-generator.agent.md",
    "reqnroll-step-definition-generator": "reqnroll-step-definition-generator.agent.md",
    "quality-gate": "quality-gate.agent.md",
    "context-converter": "context-converter.agent.md",
    "output": "output.agent.md",
    "knowledge": "knowledge.agent.md",
    "test-data": "test-data.agent.md",
    "execution": "execution.agent.md",
    "bug-reporter": "bug-reporter.agent.md",
    "metrics": "metrics.agent.md",
}


def _instruction_body(path: Path) -> str:
    value = path.read_text(encoding="utf-8")
    if value.startswith("---\n"):
        _, separator, body = value[4:].partition("\n---\n")
        if not separator:
            raise ValueError(f"Agent instruction file {path.name} has invalid frontmatter")
        value = body
    body = value.strip()
    if not body:
        raise ValueError(f"Agent instruction file {path.name} has no instruction body")
    return body


@lru_cache(maxsize=len(AGENT_FILES))
def load_agent_instructions(agent_id: str) -> str:
    """Return the instruction body from an allowlisted custom-agent Markdown file."""
    filename = AGENT_FILES.get(agent_id)
    if filename is None:
        raise KeyError(f"Unknown Markdown agent: {agent_id}")
    return _instruction_body(AGENT_DIRECTORY / filename)


@lru_cache(maxsize=64)
def load_profile_instructions(profile: str, agent_id: str | None = None) -> str:
    """Load common and optional per-agent project policy from a safe profile directory."""
    if not _PROFILE_NAME.fullmatch(profile):
        raise ValueError(
            "Agent profile must use lowercase letters, numbers, hyphens, or underscores"
        )
    directory = PROFILE_DIRECTORY / profile
    if not directory.is_dir():
        raise ValueError(f"Unknown agent profile: {profile}")
    sections = [_instruction_body(directory / "profile.md")]
    if agent_id:
        if agent_id not in AGENT_FILES:
            raise KeyError(f"Unknown Markdown agent: {agent_id}")
        override = directory / f"{agent_id}.md"
        if override.is_file():
            sections.append(_instruction_body(override))
    knowledge_directory = directory / "knowledge"
    if knowledge_directory.is_dir():
        for knowledge_file in sorted(knowledge_directory.glob("*.md")):
            sections.append(
                "PROJECT KNOWLEDGE SOURCE: "
                + knowledge_file.name
                + "\n"
                + _instruction_body(knowledge_file)
            )
    return "\n\n".join(sections)


def generation_agent_instructions(target: str, profile: str = "auto-finance-quotation") -> str:
    specialist = {
        "manual": "manual-test-generator",
        "automation": "automation-test-generator",
    }.get(target)
    sections = [
        load_agent_instructions("business-rules"),
        load_agent_instructions("reqforge"),
    ]
    sections.append(load_profile_instructions(profile, "reqforge"))
    if specialist:
        sections.append(load_agent_instructions(specialist))
        if specialist == "manual-test-generator":
            sections.append(load_agent_instructions("manual-testing-specialist"))
        specialist_override = PROFILE_DIRECTORY / profile / f"{specialist}.md"
        if specialist_override.is_file():
            sections.append(_instruction_body(specialist_override))
    sections.append(load_agent_instructions("quality-gate"))
    sections.append(load_agent_instructions("test-data"))
    quality_override = PROFILE_DIRECTORY / profile / "quality-gate.md"
    if quality_override.is_file():
        sections.append(_instruction_body(quality_override))
    return "\n\n".join(sections)


def step_definition_agent_instructions(
    profile: str = "auto-finance-quotation",
) -> str:
    """Return the base ReqnRoll policy plus the selected project's BRD profile."""
    return "\n\n".join(
        [
            load_agent_instructions("reqnroll-step-definition-generator"),
            load_profile_instructions(profile, "reqnroll-step-definition-generator"),
        ]
    )
