import pytest

from app.config import Settings
from app.generator import _json_object, create_generator, user_prompt
from app.models import GenerateRequest


def test_create_generator_always_returns_copilot() -> None:
    assert type(create_generator(Settings())).__name__ == "CopilotGenerator"


def test_json_object_accepts_accidental_markdown_fence() -> None:
    assert _json_object('```json\n{"feature_name":"Login"}\n```') == '{"feature_name":"Login"}'


def test_json_object_rejects_non_json_output() -> None:
    with pytest.raises(ValueError, match="No JSON object"):
        _json_object("I could not generate the suite")


def test_initial_prompt_requests_small_poc_suite_in_one_response() -> None:
    prompt = user_prompt(GenerateRequest(description="As a user, I want secure sign in."))
    assert "2 to 3 concise, high-level scenarios in one response" in prompt
    assert "at least 2 automation" in prompt
    assert "2 genuinely manual" in prompt
    assert "exactly the 2 highest-value cases" not in prompt


def test_bdd_prompt_requests_specflow_outlines_and_examples() -> None:
    prompt = user_prompt(
        GenerateRequest(description="As a user, I want secure sign in.", output_format="bdd")
    )
    assert "copy-ready SpecFlow syntax" in prompt
    assert "Scenario Outline" in prompt
    assert "Examples table" in prompt


def test_prompt_requires_automation_feasibility_classification() -> None:
    prompt = user_prompt(GenerateRequest(description="As a user, I want secure sign in."))
    assert "execution_mode" in prompt
    assert "feasibility_reason" in prompt


def test_manual_specialist_prompt_restricts_execution_mode() -> None:
    prompt = user_prompt(
        GenerateRequest(
            description="Explore the sign-in experience manually.", generation_target="manual"
        )
    )

    assert "Generate only manual cases" in prompt
    assert "Every execution_mode must be manual" in prompt
