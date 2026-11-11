"""Skill scope, runtime guardrails and policy changes without external provider calls."""

import shutil
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app import agent_instructions as policy
from app.agents.artifact_runner import ArtifactGenerationRunner
from app.agents.runner import CopilotAgentRunner, CopilotGenerationError, StructuredAgentDefinition
from app.config import Settings
from app.generator import system_prompt
from app.memory import OrganizationalMemory
from app.model_policy import COPILOT_MODEL
from app.models import GenerateRequest, LlmModel


@pytest.fixture
def policy_files(tmp_path, monkeypatch):
    for name in ("SKILL_DIRECTORY", "GUARDRAIL_DIRECTORY"):
        original = getattr(policy, name)
        destination = tmp_path / original.name
        shutil.copytree(original, destination)
        monkeypatch.setattr(policy, name, destination)
    return Settings(_env_file=None, user_database_path=tmp_path / "users.db")


def test_aliases_receive_scoped_skills_without_unrelated_maintenance_guidance():
    assert policy.load_agent_instructions("decision-agent") == policy.load_agent_instructions(
        "reqforge"
    )
    bdd = policy._instruction_body(policy.SKILL_DIRECTORY / policy.SKILL_FILES["bdd-automation"])
    maintenance = policy._instruction_body(
        policy.SKILL_DIRECTORY / policy.SKILL_FILES["workspace-customization"]
    )
    assert bdd in policy.load_agent_instructions("reqnroll-step-definition-generator")
    assert bdd not in policy.load_agent_instructions("business-analyst")
    assert all(
        maintenance not in policy.load_agent_instructions(agent) for agent in policy.AGENT_FILES
    )


@pytest.mark.parametrize("kind", ["skill", "guardrail"])
def test_policy_edits_refresh_instructions_and_reuse_but_keep_feedback_identity(policy_files, kind):
    request = GenerateRequest(description="Check application access and recovery requirements")
    before = policy.policy_fingerprint(policy_files)
    feedback = OrganizationalMemory.review_key_for(request)
    if kind == "skill":
        path = policy.SKILL_DIRECTORY / policy.SKILL_FILES["requirements-analysis"]

        def load():
            return policy.load_agent_instructions("business-analyst")
    else:
        path = policy.GUARDRAIL_DIRECTORY / "source-trust.md"

        def load():
            return policy.with_runtime_guardrails("Review source")

    original = load()
    path.write_text(path.read_text() + "\nUpdated project-specific review guidance.\n")
    assert load() != original
    assert policy.policy_fingerprint(policy_files) != before
    assert OrganizationalMemory.review_key_for(request) == feedback


def test_missing_registered_policy_fails_closed(policy_files):
    (policy.GUARDRAIL_DIRECTORY / "provider-and-tools.md").unlink()
    with pytest.raises(FileNotFoundError):
        policy.with_runtime_guardrails("Generate tests")
    (policy.SKILL_DIRECTORY / policy.SKILL_FILES["bdd-automation"]).unlink()
    with pytest.raises(FileNotFoundError):
        policy.load_agent_instructions("reqnroll-step-definition-generator")


def test_runtime_policy_is_last_and_is_not_duplicated_between_provider_adapters():
    source = "Role instructions followed by profile/reference context."
    guarded = policy.with_runtime_guardrails(source)
    assert guarded.startswith(source)
    assert policy.with_runtime_guardrails(guarded) == guarded
    assert guarded.endswith(policy._instruction_body(policy.AGENT_DIRECTORY / "model-policy.md"))
    assert policy.with_runtime_guardrails(guarded + "\nMore reference context.") != guarded


def test_direct_suite_provider_prompt_receives_shared_guardrails():
    request = GenerateRequest(description="Check application access and recovery requirements")
    instructions = system_prompt(request, "testpilot", Settings(_env_file=None))
    for name in policy.GUARDRAIL_FILES:
        assert policy._instruction_body(policy.GUARDRAIL_DIRECTORY / name) in instructions


class ExampleArtifact(BaseModel):
    value: str


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route", [LlmModel.CODEX, LlmModel.OPENAI, LlmModel.GEMINI, LlmModel.CLAUDE_HAIKU_4_5]
)
async def test_each_artifact_provider_keeps_guardrails_during_validation_repair(route):
    runner = ArtifactGenerationRunner(Settings(_env_file=None))
    result = ExampleArtifact(value="ready")
    provider = AsyncMock(return_value=result)
    if route == LlmModel.CLAUDE_HAIKU_4_5:
        runner.copilot.generate_structured = provider
    else:
        setattr(
            runner,
            {LlmModel.CODEX: "_codex", LlmModel.OPENAI: "_openai", LlmModel.GEMINI: "_gemini"}[
                route
            ],
            provider,
        )
    attempts = 0

    def validate(artifact):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("Correct the incomplete artifact")
        return artifact

    definition = StructuredAgentDefinition(
        output_model=ExampleArtifact,
        timeout_error="timeout",
        empty_error="empty",
        invalid_error="invalid",
    )
    assert (
        await runner.generate_structured(
            definition,
            instructions="Stage policy",
            prompt="Source data",
            llm_model=route,
            validate=validate,
        )
        == result
    )
    assert provider.await_count == 2
    for call in provider.await_args_list:
        instructions = call.kwargs["instructions"] if call.kwargs else call.args[1]
        for name in policy.GUARDRAIL_FILES:
            assert policy._instruction_body(policy.GUARDRAIL_DIRECTORY / name) in instructions


@pytest.mark.asyncio
async def test_copilot_schema_repair_boundary_retains_model_and_tool_restrictions():
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.create_session.side_effect = RuntimeError("stop before generation")
    runner = CopilotAgentRunner(Settings(_env_file=None), lambda **kwargs: client)
    with pytest.raises(CopilotGenerationError):
        await runner.invoke(
            instructions=policy.load_agent_section("output", "Schema repair role"),
            prompt="Untrusted output to repair",
            timeout_error="timeout",
        )
    options = client.create_session.call_args.kwargs
    for name in policy.GUARDRAIL_FILES:
        assert (
            policy._instruction_body(policy.GUARDRAIL_DIRECTORY / name)
            in options["system_message"]["content"]
        )
    assert options["model"] == COPILOT_MODEL
    assert options["enable_skills"] is False
    assert options["enable_config_discovery"] is False
    assert options["available_tools"] == []
