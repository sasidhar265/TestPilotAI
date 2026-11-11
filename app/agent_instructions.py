"""Load repository-owned Markdown agent policies for the governed runtime."""

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

AGENT_DIRECTORY = Path(__file__).parent.parent / ".github" / "agents"
PROFILE_DIRECTORY = Path(__file__).parent.parent / ".github" / "agent-profiles"
SKILL_DIRECTORY = Path(__file__).parent.parent / ".github" / "skills"
GUARDRAIL_DIRECTORY = Path(__file__).parent.parent / ".github" / "guardrails"
SKILL_FILES = {
    name: f"{name}/SKILL.md"
    for name in (
        "requirements-analysis",
        "reviewed-test-design",
        "bdd-automation",
        "execution-evidence",
        "knowledge-maintenance",
        "workspace-customization",
    )
}
# Keys match canonical agent filenames; aliases resolve through AGENT_FILES below.
AGENT_SKILLS = {
    "business-analyst": ("requirements-analysis",),
    "requirements-validation": ("requirements-analysis",),
    "business-rules": ("requirements-analysis",),
    "context-converter": ("requirements-analysis",),
    "reqforge": ("reviewed-test-design",),
    "story-generator": ("reviewed-test-design",),
    "scenario-generator": ("reviewed-test-design",),
    "workflow-test-cases": ("reviewed-test-design",),
    "manual-test-generator": ("reviewed-test-design",),
    "manual-testing-specialist": ("reviewed-test-design",),
    "automation-test-generator": ("reviewed-test-design", "bdd-automation"),
    "reqnroll-step-definition-generator": ("bdd-automation",),
    "multi-language": ("bdd-automation",),
    "quality-gate": ("reviewed-test-design", "bdd-automation", "execution-evidence"),
    "knowledge": ("knowledge-maintenance",),
    "testpilot-coordinator": ("reviewed-test-design", "knowledge-maintenance"),
    "execution": ("execution-evidence",),
    "bug-reporter": ("execution-evidence",),
    "metrics": ("execution-evidence",),
    "output": ("execution-evidence",),
}
GUARDRAIL_FILES = (
    "source-trust.md",
    "workflow-approval.md",
    "provider-and-tools.md",
    "execution-evidence.md",
)
_PROFILE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
AGENT_FILES = {
    "business-analyst": "business-analyst.agent.md",
    "requirements-validation": "requirements-validation.agent.md",
    "story-generator": "story-generator.agent.md",
    "scenario-generator": "scenario-generator.agent.md",
    "workflow-test-cases": "workflow-test-cases.agent.md",
    "multi-language": "multi-language.agent.md",
    "business-rules": "business-rules.agent.md",
    "reqforge": "reqforge.agent.md",
    "decision-agent": "reqforge.agent.md",
    "testpilot-coordinator": "testpilot-coordinator.agent.md",
    "orchestrator-agent": "testpilot-coordinator.agent.md",
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


def load_agent_instructions(agent_id: str) -> str:
    """Return the instruction body from an allowlisted custom-agent Markdown file."""
    filename = AGENT_FILES.get(agent_id)
    if filename is None:
        raise KeyError(f"Unknown Markdown agent: {agent_id}")
    sections = [_instruction_body(AGENT_DIRECTORY / filename)]
    skill_ids = AGENT_SKILLS.get(filename.removesuffix(".agent.md"), ())
    if skill_ids:
        sections.append("## Application skills")
        sections.extend(
            _instruction_body(SKILL_DIRECTORY / SKILL_FILES[name]) for name in skill_ids
        )
    sections.append(_instruction_body(AGENT_DIRECTORY / "model-policy.md"))
    return "\n\n".join(sections)


def with_runtime_guardrails(instructions: str) -> str:
    """Append trusted policy at the provider boundary, including schema repairs and retries."""
    policy = "\n\n".join(
        [
            "## Application runtime guardrails",
            *(_instruction_body(GUARDRAIL_DIRECTORY / name) for name in GUARDRAIL_FILES),
            _instruction_body(AGENT_DIRECTORY / "model-policy.md"),
        ]
    )
    # An artifact call may already have passed through this boundary before reaching Copilot.
    if instructions.endswith(policy):
        return instructions
    return instructions + "\n\n" + policy


def profile_knowledge_sources(
    profile: str, settings: "Settings | None" = None
) -> list[dict[str, str]]:
    """Expose the same reference documents used in prompts, without granting approval."""
    if not _PROFILE_NAME.fullmatch(profile):
        raise ValueError("Invalid agent profile name")
    directory = PROFILE_DIRECTORY / profile
    if not directory.is_dir():
        from app.config import get_settings
        from app.domain_profiles import DomainProfileStore

        custom = DomainProfileStore((settings or get_settings()).user_database_path).custom(profile)
        if custom:
            return [
                {
                    "id": f"profile-{profile}",
                    "title": custom["name"],
                    "authority": "reference_only",
                    "path": "/settings#domain-profile-settings",
                    "content": custom["instructions"],
                }
            ]
        raise ValueError(f"Unknown agent profile: {profile}")
    sources = []
    for path in sorted((directory / "knowledge").glob("*.md")):
        content = _instruction_body(path)
        sources.append(
            {
                "id": path.name,
                "title": content.splitlines()[0].removeprefix("# "),
                "authority": "reference_only",
                "path": str(path.relative_to(PROFILE_DIRECTORY.parent.parent)),
                "content": content,
            }
        )
    return sources


def load_profile_instructions(
    profile: str, agent_id: str | None = None, settings: "Settings | None" = None
) -> str:
    """Load common and optional per-agent project policy from a safe profile directory."""
    if not _PROFILE_NAME.fullmatch(profile):
        raise ValueError(
            "Agent profile must use lowercase letters, numbers, hyphens, or underscores"
        )
    directory = PROFILE_DIRECTORY / profile
    if not directory.is_dir():
        from app.config import get_settings
        from app.domain_profiles import DomainProfileStore

        custom = DomainProfileStore((settings or get_settings()).user_database_path).custom(profile)
        if custom:
            if agent_id and agent_id not in AGENT_FILES:
                raise KeyError(f"Unknown Markdown agent: {agent_id}")
            return "UI-MANAGED DOMAIN PROFILE (supplements mandatory base policies):\n" + str(
                custom["instructions"]
            )
        raise ValueError(f"Unknown agent profile: {profile}")
    sections = [_instruction_body(directory / "profile.md")]
    if agent_id:
        if agent_id not in AGENT_FILES:
            raise KeyError(f"Unknown Markdown agent: {agent_id}")
        override = directory / f"{agent_id}.md"
        if override.is_file():
            sections.append(_instruction_body(override))
    for source in profile_knowledge_sources(profile, settings):
        sections.append("PROJECT KNOWLEDGE SOURCE: " + source["id"] + "\n" + source["content"])
    return "\n\n".join(sections)


def generation_agent_instructions(
    target: str, profile: str = "auto-finance-quotation", settings: "Settings | None" = None
) -> str:
    specialist = {
        "manual": "manual-test-generator",
        "automation": "automation-test-generator",
    }.get(target)
    sections = [
        load_agent_instructions("business-rules"),
        load_agent_instructions("decision-agent"),
    ]
    sections.append(load_profile_instructions(profile, "decision-agent", settings))
    if specialist:
        sections.append(load_agent_instructions(specialist))
        if specialist == "manual-test-generator":
            sections.append(load_agent_instructions("manual-testing-specialist"))
        specialist_override = PROFILE_DIRECTORY / profile / f"{specialist}.md"
        if specialist_override.is_file():
            sections.append(_instruction_body(specialist_override))
    sections.append(load_agent_instructions("quality-gate"))
    from app.workspace_policy import standards

    sections.append(standards("feature"))
    from app.quotation_contract import quotation_instructions

    sections.append(quotation_instructions())
    quality_override = PROFILE_DIRECTORY / profile / "quality-gate.md"
    if quality_override.is_file():
        sections.append(_instruction_body(quality_override))
    return "\n\n".join(sections)


def step_definition_agent_instructions(
    profile: str = "auto-finance-quotation",
    settings: "Settings | None" = None,
) -> str:
    """Return the base ReqnRoll policy plus the selected project's BRD profile."""
    from app.quotation_contract import quotation_instructions
    from app.workspace_policy import standards

    return "\n\n".join(
        [
            load_agent_instructions("reqnroll-step-definition-generator"),
            load_profile_instructions(profile, "reqnroll-step-definition-generator", settings),
            standards("automation"),
            standards("feature"),
            quotation_instructions(),
        ]
    )


def load_agent_section(agent_id: str, heading: str) -> str:
    """Read an explicitly named policy section afresh for every invocation."""
    body = load_agent_instructions(agent_id)
    marker = f"## {heading}\n"
    sections = body.split(marker)
    if len(sections) != 2:
        raise ValueError(f"Agent {agent_id} must define exactly one {heading!r} section")
    section = re.split(r"^## ", sections[1], maxsplit=1, flags=re.MULTILINE)[0].strip()
    if not section:
        raise ValueError(f"Agent {agent_id} has an empty {heading!r} section")
    return "\n" + section + "\n"


def policy_fingerprint(settings: "Settings | None" = None) -> str:
    """Invalidate generated-suite reuse when agent policy or project knowledge changes."""
    import hashlib

    digest = hashlib.sha256()
    for directory in (AGENT_DIRECTORY, PROFILE_DIRECTORY, SKILL_DIRECTORY, GUARDRAIL_DIRECTORY):
        for path in sorted(directory.rglob("*.md")):
            digest.update(f"{directory.name}/{path.relative_to(directory)}".encode())
            digest.update(path.read_bytes())
    from app.config import get_settings
    from app.domain_profiles import profile_fingerprint
    from app.knowledge_agents import published_fingerprint

    configuration = settings or get_settings()
    digest.update(published_fingerprint(configuration).encode())
    digest.update(profile_fingerprint(configuration).encode())
    return digest.hexdigest()
