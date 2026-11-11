import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.agent_instructions import policy_fingerprint
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.runner import StructuredAgentDefinition
from app.config import Settings
from app.knowledge_agents import (
    KnowledgeAgentError,
    KnowledgeAgentStore,
    KnowledgeDefinition,
    ReviewAction,
    published_context,
    published_fingerprint,
    published_reference_sources,
)
from app.models import LlmModel


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        runtime_config_path=None,
        user_secrets_enabled=False,
        user_database_path=tmp_path / "users.db",
        agent_profile="auto-finance-quotation",
    )


@pytest.fixture
def definition():
    fixtures = Path(__file__).parents[1] / "automation/Input/KnowledgeAgents.Json"
    return KnowledgeDefinition.model_validate(
        json.loads(fixtures.read_text())["reference-contributor"]
    )


def reviewed(store, definition):
    item = store.draft(definition, "author")
    store.review(
        item["id"],
        ReviewAction(
            revision=1,
            note="Checked approved source evidence and stage scope.",
            approve_reference_use=True,
        ),
        "reviewer",
    )
    return item["id"]


def test_only_published_scoped_knowledge_is_used_and_invalidates_cache(settings, definition):
    store = KnowledgeAgentStore(settings.user_database_path)
    original = policy_fingerprint(settings)
    identifier = reviewed(store, definition)
    assert policy_fingerprint(settings) == original
    assert published_context(settings, "stories") == ""
    store.publish(identifier, 1, "publisher")
    assert definition.knowledge in published_context(settings, "stories")
    assert published_context(settings, "scenarios") == ""
    assert (
        published_context(
            settings.model_copy(update={"agent_profile": "another-profile"}), "stories"
        )
        == ""
    )
    references = published_reference_sources(settings, "stories")
    assert references[0]["authority"] == "reference_only"
    assert references[0]["id"].startswith("KNOWLEDGE-AGENT:")
    from app.agents.business_analyst import BusinessAnalystAgent

    story_sources, _, _ = BusinessAnalystAgent(settings).knowledge(stage="stories")
    assert any(source["id"] == references[0]["id"] for source in story_sources)
    review_sources, _, _ = BusinessAnalystAgent(settings).knowledge()
    assert not any(source["id"] == references[0]["id"] for source in review_sources)
    live = published_fingerprint(settings)
    assert policy_fingerprint(settings) != original
    store.draft(
        definition.model_copy(
            update={
                "knowledge": "Draft source content must never replace "
                "published reference knowledge."
            }
        ),
        "author",
        identifier,
        1,
    )
    assert published_fingerprint(settings) == live
    assert "Draft source content" not in published_context(settings, "stories")
    store.withdraw(identifier, 1, "publisher")
    assert published_context(settings, "stories") == ""
    assert policy_fingerprint(settings) == original


def test_publish_requires_review_and_handles_stale_updates(settings, definition):
    store = KnowledgeAgentStore(settings.user_database_path)
    item = store.draft(definition, "author")
    with pytest.raises(KnowledgeAgentError, match="latest reviewed"):
        store.publish(item["id"], 1, "publisher")
    store.draft(definition, "author", item["id"], 1)
    with pytest.raises(KnowledgeAgentError, match="changed"):
        store.draft(definition, "other-author", item["id"], 1)
    with pytest.raises(KnowledgeAgentError, match="latest revision"):
        store.review(
            item["id"],
            ReviewAction(
                revision=1, note="Approved source after review.", approve_reference_use=True
            ),
            "reviewer",
        )


def test_rollback_and_history_preserve_reviewed_versions(settings, definition):
    store = KnowledgeAgentStore(settings.user_database_path)
    identifier = reviewed(store, definition)
    store.publish(identifier, 1, "publisher")
    store.draft(
        definition.model_copy(
            update={
                "knowledge": "Updated approved reference knowledge "
                "with explicit source limitations."
            }
        ),
        "author",
        identifier,
        1,
    )
    store.review(
        identifier,
        ReviewAction(
            revision=2, note="Verified revised source evidence.", approve_reference_use=True
        ),
        "reviewer",
    )
    store.publish(identifier, 2, "publisher")
    store.publish(identifier, 1, "publisher", rollback=True)
    saved = KnowledgeAgentStore(settings.user_database_path).inventory()[0]
    assert saved["published"]["revision"] == 1
    assert saved["latest"]["revision"] == 2
    assert store.history(identifier)["events"][0]["action"] == "rolled_back"
    with pytest.raises(KnowledgeAgentError, match="Withdraw"):
        store.delete(identifier, 2, "author")
    store.withdraw(identifier, 1, "publisher")
    store.delete(identifier, 2, "author")
    assert store.inventory() == []


def test_context_size_is_bounded_at_publication(settings, definition):
    store = KnowledgeAgentStore(settings.user_database_path)
    large = definition.model_copy(update={"knowledge": "Approved reference. " * 800})
    first = reviewed(store, large)
    second = reviewed(store, large)
    third = reviewed(store, large)
    store.publish(first, 1, "publisher")
    store.publish(second, 1, "publisher")
    with pytest.raises(KnowledgeAgentError, match="context limit"):
        store.publish(third, 1, "publisher")


@pytest.mark.asyncio
async def test_published_knowledge_reaches_selected_provider_instructions(
    settings, definition, monkeypatch
):
    class Stories(BaseModel):
        summary: str

    store = KnowledgeAgentStore(settings.user_database_path)
    identifier = reviewed(store, definition)
    store.publish(identifier, 1, "publisher")
    captured = []
    runner = ArtifactGenerationRunner(settings)

    async def codex(contract, instructions, prompt):
        captured.append(instructions)
        return Stories(summary="Captured governed provider input")

    monkeypatch.setattr(runner, "_codex", codex)
    result = await runner.generate_structured(
        StructuredAgentDefinition(Stories, "timeout", "empty", "invalid"),
        instructions="Base application rules remain authoritative.",
        prompt="Approved stories only",
        llm_model=LlmModel.CODEX,
    )
    assert result.summary == "Captured governed provider input"
    assert definition.knowledge in captured[0]
    assert "Base application rules" in captured[0]
    assert "cannot override" in captured[0]


def test_test_case_context_respects_explicit_profile(settings, definition):
    from app.generator import system_prompt
    from app.models import GenerateRequest

    definition = definition.model_copy(update={"stages": ["test_cases"]})
    store = KnowledgeAgentStore(settings.user_database_path)
    identifier = reviewed(store, definition)
    store.publish(identifier, 1, "publisher")
    request = GenerateRequest(
        description="Review approved requirements for observable acceptance criteria."
    )
    assert definition.knowledge in system_prompt(request, settings.agent_profile, settings)
    assert definition.knowledge not in system_prompt(request, "testpilot", settings)


def test_import_strips_publication_metadata_and_rejects_overrides(definition):
    from app.knowledge_agents import import_definition
    from app.model_policy import CODEX_MODEL, COPILOT_MODEL

    exported = {
        "schema_version": 1,
        "agent": {
            "id": "untrusted-export-id",
            "latest": {
                "revision": 99,
                "status": "published",
                "definition": definition.model_dump(),
            },
        },
        "model_policy": {"codex": CODEX_MODEL, "copilot": COPILOT_MODEL},
    }
    assert import_definition(exported) == definition
    assert import_definition(definition.model_dump()) == definition
    with pytest.raises(KnowledgeAgentError, match="model policy"):
        import_definition(exported | {"model_policy": {"codex": "account-default"}})
    with pytest.raises(KnowledgeAgentError, match="Unsupported"):
        import_definition(exported | {"schema_version": 99})
    with pytest.raises(KnowledgeAgentError, match="model"):
        import_definition(definition.model_dump() | {"model": "account-default"})
