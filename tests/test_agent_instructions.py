import pytest

from app import agent_runtime, generator
from app.agent_instructions import (
    load_agent_instructions,
    load_profile_instructions,
    step_definition_agent_instructions,
)


@pytest.mark.parametrize(
    "agent_id",
    [
        "specforge",
        "testpilot-coordinator",
        "manual-test-generator",
        "automation-test-generator",
        "reqnroll-step-definition-generator",
        "quality-gate",
        "context-converter",
        "output",
    ],
)
def test_markdown_agent_instruction_body_is_loadable(agent_id: str) -> None:
    body = load_agent_instructions(agent_id)

    assert body.startswith("You are")
    assert "---" not in body


def test_reqnroll_generator_requires_reusable_http_client_api_scripts() -> None:
    body = load_agent_instructions("reqnroll-step-definition-generator")

    assert "HttpClient" in body
    assert "IHttpClientFactory" in body
    assert "typed API client" in body
    assert "do not introduce RestSharp" in body


def test_coordinator_workflow_is_loaded_from_markdown() -> None:
    body = load_agent_instructions("testpilot-coordinator")

    assert "You are the QA Master Agent" in body
    assert "input ingested\nfrom the UI" in body
    assert "Design the risk-based test scenarios first" in body
    assert "SpecForge" in body
    assert "Always check organizational memory first" in body
    assert "Store only a passing suite" in body


def test_python_modules_do_not_embed_agent_system_prompts() -> None:
    assert not hasattr(generator, "SYSTEM_PROMPT")
    assert not hasattr(agent_runtime, "AGENT_SYSTEM_PROMPT")


def test_markdown_defines_input_output_and_manual_bdd_formats() -> None:
    specforge = load_agent_instructions("specforge")
    manual = load_agent_instructions("manual-test-generator")
    automation = load_agent_instructions("automation-test-generator")
    quality_gate = load_agent_instructions("quality-gate")

    assert "## Input contract" in specforge
    assert "## Canonical output contract" in specforge
    assert "scenario-to-test-case transformation agent" in specforge
    assert "requested `output_format`" in specforge
    assert "## Manual test-case format" in manual
    assert '"gherkin": null' in manual
    assert "## Automation test-case and scenario format" in automation
    assert "Scenario Outline:" in automation
    assert "Every placeholder must have a matching Examples column" in automation
    assert "## Required validation checklist" in quality_gate


@pytest.mark.parametrize(
    "agent_id",
    [
        "business-rules",
        "context-converter",
        "knowledge",
        "output",
        "execution",
        "bug-reporter",
        "metrics",
        "test-data",
        "testpilot-coordinator",
        "reqnroll-step-definition-generator",
    ],
)
def test_support_agent_markdown_has_structured_contract(agent_id: str) -> None:
    body = load_agent_instructions(agent_id)

    assert "## Inputs" in body
    assert "## Validations" in body
    assert "## Outputs" in body


def test_unknown_markdown_agent_is_rejected() -> None:
    with pytest.raises(KeyError, match="Unknown Markdown agent"):
        load_agent_instructions("unapproved-agent")


def test_project_profile_loads_common_and_agent_override() -> None:
    body = load_profile_instructions("testpilot", "automation-test-generator")

    assert "TestPilot project profile" in body
    assert "TestPilot automation override" in body
    assert "SpecFlow" in body


def test_reqnroll_instructions_include_auto_finance_brd_profile() -> None:
    body = step_definition_agent_instructions("auto-finance-quotation")

    assert "ReqnRoll Step Definition Generator" in body
    assert "domain requirements source" in body
    assert "POST /api/v1/quotations" in body
    assert "all nineteen BRD business errors" in body
    assert "UK Quotation Services ReqnRoll policy" in body


@pytest.mark.parametrize("profile", ["../secret", "Team Name", "", "UPPERCASE"])
def test_unsafe_profile_names_are_rejected(profile: str) -> None:
    with pytest.raises(ValueError, match="Agent profile"):
        load_profile_instructions(profile)


def test_unknown_safe_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown agent profile"):
        load_profile_instructions("missing-team")
