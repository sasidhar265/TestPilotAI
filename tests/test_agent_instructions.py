import pytest

from app.agent_instructions import load_agent_instructions, load_profile_instructions


@pytest.mark.parametrize(
    "agent_id",
    [
        "specforge",
        "manual-test-generator",
        "automation-test-generator",
        "quality-gate",
        "context-converter",
        "output",
    ],
)
def test_markdown_agent_instruction_body_is_loadable(agent_id: str) -> None:
    body = load_agent_instructions(agent_id)

    assert body.startswith("You are")
    assert "---" not in body


def test_unknown_markdown_agent_is_rejected() -> None:
    with pytest.raises(KeyError, match="Unknown Markdown agent"):
        load_agent_instructions("unapproved-agent")


def test_project_profile_loads_common_and_agent_override() -> None:
    body = load_profile_instructions("testpilot", "automation-test-generator")

    assert "TestPilot project profile" in body
    assert "TestPilot automation override" in body
    assert "SpecFlow" in body


@pytest.mark.parametrize("profile", ["../secret", "Team Name", "", "UPPERCASE"])
def test_unsafe_profile_names_are_rejected(profile: str) -> None:
    with pytest.raises(ValueError, match="Agent profile"):
        load_profile_instructions(profile)


def test_unknown_safe_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown agent profile"):
        load_profile_instructions("missing-team")
