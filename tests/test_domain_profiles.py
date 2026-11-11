import json

import pytest
from pydantic import ValidationError

from app.agent_instructions import (
    load_profile_instructions,
    policy_fingerprint,
    profile_knowledge_sources,
)
from app.agents.business_analyst import BusinessAnalystAgent
from app.config import Settings
from app.domain_profiles import (
    DomainProfile,
    DomainProfileStore,
    ProfileSelection,
    baseline_bytes,
    effective_settings,
)
from app.knowledge_agents import KnowledgeAgentError
from app.model_policy import CODEX_MODEL, COPILOT_MODEL


@pytest.fixture
def configuration(tmp_path):
    baseline = tmp_path / "original.json"
    baseline.write_text('{"sources": []}')
    return Settings(
        _env_file=None,
        runtime_config_path=None,
        user_database_path=tmp_path / "users.db",
        requirements_baseline_path=baseline,
    )


@pytest.fixture
def profile():
    return DomainProfile(
        id="healthcare-quality",
        name="Healthcare quality",
        description="Scope test generation to supplied healthcare workflow requirements.",
        instructions=(
            "Use approved healthcare requirements and report missing rules. "
            "Do not invent eligibility or clinical decisions."
        ),
        baseline={"sources": []},
        review_note="Checked the domain scope and source-approval metadata.",
        confirmed=True,
    )


def test_selection_is_live_and_keeps_baselines_and_models_isolated(
    configuration, profile, monkeypatch
):
    from app import config

    storage = DomainProfileStore(configuration.user_database_path)
    storage.save(profile, "reviewer")
    monkeypatch.setattr(config, "_base_settings", lambda: configuration)
    old = config.get_settings()
    original = policy_fingerprint(old)
    storage.activate(ProfileSelection(profile=profile.id, expected_revision=0), old.agent_profile)
    selected = config.get_settings()
    assert selected.agent_profile == profile.id
    assert old.agent_profile == "auto-finance-quotation"
    assert not selected.auto_finance_domain_enabled
    assert json.loads(baseline_bytes(selected)) == {"sources": []}
    assert profile.instructions in load_profile_instructions(profile.id, settings=selected)
    assert profile_knowledge_sources(profile.id, selected)[0]["authority"] == "reference_only"
    assert policy_fingerprint(selected) != original
    assert selected.codex_model == CODEX_MODEL
    assert selected.copilot_model == COPILOT_MODEL
    assert configuration.requirements_baseline_path.read_text() == '{"sources": []}'
    sources, _, limitations = BusinessAnalystAgent(selected).knowledge()
    assert not any(source["authority"] == "approved_business_source" for source in sources)
    assert not any(source["id"].startswith("UK-AUTO-FINANCE") for source in sources)
    assert limitations


def test_profile_sources_preserve_approval_status(configuration, profile):
    source = {
        "id": "CARE-SOURCE",
        "version": "1",
        "title": "Supplied service requirements",
        "status": "draft",
        "approved_by": "",
        "effective_from": "2020-01-01",
        "expires_on": None,
        "content": "Only explicitly approved requirements can define expected system behaviour.",
    }
    storage = DomainProfileStore(configuration.user_database_path)
    storage.save(profile.model_copy(update={"baseline": {"sources": [source]}}), "reviewer")
    storage.activate(
        ProfileSelection(profile=profile.id, expected_revision=0), configuration.agent_profile
    )
    selected = effective_settings(configuration)
    sources, _, _ = BusinessAnalystAgent(selected).knowledge()
    assert not any(item["id"] == source["id"] for item in sources)
    source["status"] = "approved"
    source["approved_by"] = "Business owner"
    storage.save(
        profile.model_copy(update={"baseline": {"sources": [source]}, "expected_revision": 1}),
        "reviewer",
    )
    sources, _, _ = BusinessAnalystAgent(selected).knowledge()
    assert any(
        item["id"] == source["id"] and item["authority"] == "approved_business_source"
        for item in sources
    )


def test_profiles_reject_stale_edits_and_protect_builtins(configuration, profile):
    storage = DomainProfileStore(configuration.user_database_path)
    storage.save(profile, "reviewer")
    with pytest.raises(KnowledgeAgentError, match="changed"):
        storage.save(profile, "other-reviewer")
    with pytest.raises(KnowledgeAgentError, match="Built-in"):
        storage.save(profile.model_copy(update={"id": "testpilot"}), "reviewer")
    storage.activate(
        ProfileSelection(profile=profile.id, expected_revision=0), configuration.agent_profile
    )
    with pytest.raises(KnowledgeAgentError, match="changed"):
        storage.activate(
            ProfileSelection(profile="testpilot", expected_revision=0), configuration.agent_profile
        )
    with pytest.raises(KnowledgeAgentError, match="another profile"):
        storage.delete(profile.id, 1, configuration.agent_profile)
    storage.activate(
        ProfileSelection(profile="auto-finance-quotation", expected_revision=1),
        configuration.agent_profile,
    )
    storage.delete(profile.id, 1, configuration.agent_profile)
    assert storage.custom(profile.id) is None


def test_profile_validation_does_not_allow_model_overrides_or_false_approval(
    configuration, profile
):
    with pytest.raises(ValidationError):
        DomainProfile.model_validate(profile.model_dump() | {"model": "account-default"})
    invalid = profile.model_copy(update={"baseline": {"sources": [{"id": "SOURCE"}]}})
    with pytest.raises(KnowledgeAgentError, match="baseline JSON is invalid"):
        DomainProfileStore(configuration.user_database_path).save(invalid, "reviewer")
