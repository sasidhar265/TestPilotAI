import pytest

from app.config import Settings
from app.generator import (
    _json_object,
    _normalize_suite_payload,
    create_generator,
    system_prompt,
    user_prompt,
)
from app.models import GenerateRequest
from app.models import TestSuite as SuiteModel


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


def test_system_prompt_loads_repository_markdown_agent_policies() -> None:
    prompt = system_prompt(
        GenerateRequest(
            description="Generate automated sign-in coverage for the customer portal.",
            generation_target="automation",
        ),
        profile="testpilot",
    )

    assert "You are SpecForge" in prompt
    assert "You are the Automation Test Generator" in prompt
    assert "You are the Quality Gate" in prompt
    assert "TestPilot project profile" in prompt
    assert "TestPilot automation override" in prompt
    assert "You are the Manual Test Generator" not in prompt


def test_auto_finance_profile_feeds_brd_rules_to_generation() -> None:
    prompt = system_prompt(
        GenerateRequest(
            description="Generate automated PCP quotation coverage.",
            generation_target="automation",
        )
    )

    assert "Auto Finance Quotation Service profile" in prompt
    assert "BR-018 Deposit" in prompt
    assert "NFR-005 Idempotency" in prompt
    assert "INVALID_FINANCE_TERM" in prompt
    assert "Amount financed normally equals" in prompt


def test_prompt_maps_requested_qa_labels_to_canonical_schema() -> None:
    prompt = user_prompt(
        GenerateRequest(
            description="Generate API cases with Requirement ID and HTTP Status fields.",
            generation_target="automation",
        )
    )

    assert "Map Test Case ID to id" in prompt
    assert "HTTP Status to tags" in prompt
    assert "do not return a Markdown table" in prompt


def test_normalizer_accepts_common_api_test_case_presentation_labels() -> None:
    payload = {
        "Feature": "Auto Finance Quotation API",
        "Test Cases": [
            {
                "Test Case ID": "TC-BR017-001",
                "Requirement ID": "BR-017",
                "Scenario": "Reject a request without vehicle ID",
                "Preconditions": ["Authenticated API consumer"],
                "Test Data": {"vehicleId": "missing", "cashPrice": 30000},
                "Steps": [
                    {
                        "Step": "POST /api/v1/quotes without vehicleId",
                        "Expected Result": "A mandatory-field validation error is returned",
                    }
                ],
                "Expected Result": "The quotation is not created",
                "HTTP Status": 400,
                "Priority": "P0",
                "Test Type": "Negative",
                "Automation Candidate": "Yes",
            }
        ],
    }

    suite = SuiteModel.model_validate(_normalize_suite_payload(payload))
    case = suite.test_cases[0]

    assert suite.feature_name == "Auto Finance Quotation API"
    assert case.id == "TC-BR017-001"
    assert case.acceptance_criteria_covered == ["BR-017"]
    assert case.execution_mode == "automation"
    assert "http-status:400" in case.tags
    assert case.steps[0].expected_result == "A mandatory-field validation error is returned"
