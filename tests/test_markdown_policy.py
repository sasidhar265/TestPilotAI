import pytest

from app import agent_instructions, workspace_policy
from app.agent_instructions import generation_agent_instructions, load_agent_instructions
from app.agents.implementation_approval import implementation_approval_policy
from app.automation_layout import layout_instructions
from app.memory import OrganizationalMemory
from app.models import BusinessRule, GenerateRequest


@pytest.fixture
def agent_files(tmp_path, monkeypatch):
    directory = tmp_path / "agents"
    directory.mkdir()
    for path in agent_instructions.AGENT_DIRECTORY.glob("*.md"):
        (directory / path.name).write_bytes(path.read_bytes())
    monkeypatch.setattr(agent_instructions, "AGENT_DIRECTORY", directory)
    monkeypatch.setattr(workspace_policy, "RULES_PATH", directory / "business-rules.agent.md")
    return directory


def test_editing_agent_policy_refreshes_prompt_and_memory_but_preserves_reviews(agent_files):
    request = GenerateRequest(description="Check account access permissions")
    before = OrganizationalMemory.key_for(request)
    review = OrganizationalMemory.review_key_for(request)
    original = generation_agent_instructions("manual")
    path = agent_files / "manual-test-generator.agent.md"
    path.write_text(
        path.read_text() + "\n\n## Training examples\n\nNew project training guidance.\n"
    )

    assert "New project training guidance." not in original
    assert "New project training guidance." in generation_agent_instructions("manual")
    assert OrganizationalMemory.key_for(request) != before
    assert OrganizationalMemory.review_key_for(request) == review


def test_shared_policies_are_not_frozen_at_import(agent_files):
    assert "Do not manufacture approval" in implementation_approval_policy()
    path = agent_files / "quality-gate.agent.md"
    path.write_text(
        path.read_text().replace("Do not manufacture approval", "Never manufacture approval")
    )
    assert "Never manufacture approval" in implementation_approval_policy()
    before = layout_instructions()
    path = agent_files / "automation-test-generator.agent.md"
    path.write_text(
        path.read_text().replace("Root build/dependency manifests", "Root dependency files")
    )
    assert "Root build/dependency manifests" in before
    assert "Root dependency files" in layout_instructions()


def test_rules_roundtrip_preserves_guidance_and_multiline_descriptions(agent_files):
    path = workspace_policy.RULES_PATH
    before, _, after = workspace_policy._rule_document()
    rules = [
        BusinessRule(id="BR-001", description="Reject locked accounts.\nExplain the rejection.")
    ]
    workspace_policy.save_business_rules(rules)
    assert workspace_policy.load_business_rules() == rules
    assert workspace_policy._rule_document()[::2] == (before, after)
    assert "- BR-001: Reject locked accounts.\n  Explain the rejection." in path.read_text()
    assert "Reject locked accounts." in load_agent_instructions("business-rules")
    workspace_policy.save_business_rules([])
    assert workspace_policy.load_business_rules() == []
    assert workspace_policy._rule_document()[::2] == (before, after)
    assert not list(agent_files.glob("*.json"))


@pytest.mark.parametrize("replacement", ["bad rule", "- BR-1: abc\n- BR-1: duplicate"])
def test_invalid_hand_edited_rules_fail_closed(agent_files, replacement):
    path = workspace_policy.RULES_PATH
    path.write_text(
        path.read_text().replace(
            workspace_policy.RULES_START + "\n\n",
            workspace_policy.RULES_START + "\n" + replacement + "\n",
        )
    )
    with pytest.raises(ValueError):
        workspace_policy.load_business_rules()


def test_missing_markers_do_not_overwrite_agent_guidance(agent_files):
    path = workspace_policy.RULES_PATH
    path.write_text("Agent guidance without a rules section\n")
    with pytest.raises(ValueError, match="section"):
        workspace_policy.save_business_rules([])
    assert path.read_text() == "Agent guidance without a rules section\n"


def test_profile_edits_are_loaded_without_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_instructions, "PROFILE_DIRECTORY", tmp_path)
    profile = tmp_path / "example"
    profile.mkdir()
    path = profile / "profile.md"
    path.write_text("Original project conditions")
    assert agent_instructions.load_profile_instructions("example") == "Original project conditions"
    path.write_text("Updated project conditions")
    assert agent_instructions.load_profile_instructions("example") == "Updated project conditions"
