import pytest

from app.agents.runner import CopilotGenerationError, json_object
from app.config import Settings
from app.generator import (
    FallbackGenerator,
    _codex_failure_message,
    _normalize_suite_payload,
    _strict_json_schema,
    create_generator,
    finalize_suite,
    system_prompt,
    user_prompt,
)
from app.models import GenerateRequest, GenerationSource
from app.models import TestCase as CaseModel
from app.models import TestCategory as CategoryModel
from app.models import TestStep as StepModel
from app.models import TestSuite as SuiteModel


def test_create_generator_returns_resilient_fallback() -> None:
    assert type(create_generator(Settings())).__name__ == "FallbackGenerator"


def test_codex_schema_closes_every_object_and_requires_its_properties() -> None:
    schema = _strict_json_schema(SuiteModel.model_json_schema())

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["$defs"]["TestCase"]["additionalProperties"] is False
    assert "default" not in schema["properties"]["generation_source"]


def test_codex_error_classification_does_not_scan_echoed_prompt() -> None:
    stderr = b"user prompt about authentication\nERROR: invalid_json_schema"

    assert "schema" in _codex_failure_message(stderr).casefold()


@pytest.mark.asyncio
async def test_automatic_route_falls_back_from_copilot_and_openai_to_codex() -> None:
    generator = FallbackGenerator(Settings())
    calls: list[str] = []

    async def unavailable(*args, **kwargs):
        calls.append("unavailable")
        raise CopilotGenerationError("quota exhausted")

    async def codex(*args, **kwargs):
        calls.append("codex")
        return SuiteModel(
            feature_name="Fallback suite",
            generation_source=GenerationSource.CODEX,
            test_cases=[
                CaseModel(
                    id="TC-001",
                    title="Fallback case",
                    objective="Verify fallback generation",
                    category=CategoryModel.SMOKE,
                    priority="P1",
                    execution_mode="automation",
                    feasibility_reason="Deterministic behavior",
                    steps=[StepModel(action="Generate", expected_result="Suite is returned")],
                )
            ],
        )

    generator.copilot.generate = unavailable
    generator.openai.generate = unavailable
    generator.codex.generate = codex

    result = await generator.generate(
        GenerateRequest(description="Generate test cases using automatic provider fallback.")
    )

    assert calls == ["unavailable", "unavailable", "codex"]
    assert result.generation_source == GenerationSource.CODEX


def test_json_object_accepts_accidental_markdown_fence() -> None:
    assert json_object('```json\n{"feature_name":"Login"}\n```') == '{"feature_name":"Login"}'


def test_json_object_rejects_non_json_output() -> None:
    with pytest.raises(ValueError, match="No JSON object"):
        json_object("I could not generate the suite")


def test_request_prompt_contains_data_not_agent_policy() -> None:
    prompt = user_prompt(GenerateRequest(description="As a user, I want secure sign in."))

    assert '"phase": "initial"' in prompt
    assert '"generation_target": "auto"' in prompt
    assert '"manual_testing_type": "api"' in prompt
    assert "As a user, I want secure sign in." in prompt
    assert "Generate two or three" not in prompt
    assert "Generate only manual cases" not in prompt


def test_markdown_policy_requests_specflow_outlines_and_examples() -> None:
    prompt = system_prompt(
        GenerateRequest(
            description="Automate secure sign in.",
            output_format="bdd",
            generation_target="automation",
        ),
        profile="testpilot",
    )

    assert "copy-ready SpecFlow Gherkin" in prompt
    assert "Scenario Outline" in prompt
    assert "complete `Examples`" in prompt


def test_prompt_requires_automation_feasibility_classification() -> None:
    prompt = system_prompt(GenerateRequest(description="As a user, I want secure sign in."))
    assert "execution_mode" in prompt
    assert "feasibility_reason" in prompt
    assert "scenario_group" in prompt
    assert "duplicated standalone case" in prompt


def test_finalized_cases_are_grouped_and_common_duplicates_are_removed() -> None:
    common = CaseModel(
        id="TC-002",
        scenario_group="Account sign in",
        title="Reject invalid password",
        objective="Verify invalid credentials are rejected",
        category=CategoryModel.REGRESSION,
        priority="P1",
        execution_mode="automation",
        feasibility_reason="Stable authentication response",
        steps=[StepModel(action="Submit an invalid password", expected_result="Access is denied")],
    )
    suite = SuiteModel(
        feature_name="Authentication",
        test_cases=[
            common,
            common.model_copy(update={"id": "TC-003"}),
            common.model_copy(
                update={
                    "id": "TC-001",
                    "scenario_group": "Account recovery",
                    "title": "Request password reset",
                    "objective": "Verify password reset can be requested",
                }
            ),
        ],
    )

    result = finalize_suite(
        suite, GenerateRequest(description="Verify account authentication journeys.")
    )

    assert len(result.test_cases) == 2
    assert [case.scenario_group for case in result.test_cases] == [
        "Account recovery",
        "Account sign in",
    ]


def test_manual_specialist_prompt_restricts_execution_mode() -> None:
    prompt = system_prompt(
        GenerateRequest(
            description="Explore the sign-in experience manually.", generation_target="manual"
        ),
        profile="testpilot",
    )

    assert "Produce only cases whose `execution_mode` is `manual`" in prompt


def test_system_prompt_loads_repository_markdown_agent_policies() -> None:
    prompt = system_prompt(
        GenerateRequest(
            description="Generate automated sign-in coverage for the customer portal.",
            generation_target="automation",
        ),
        profile="testpilot",
    )

    assert "You are DecisionAgent" in prompt
    assert "You are the Automation Test Generator" in prompt
    assert "You are the Quality Gate" in prompt
    assert "Quality Lifecycle Studio default project profile" in prompt
    assert "Quality Lifecycle Studio automation override" in prompt
    assert "You are the Manual Test Generator" not in prompt


def test_auto_finance_profile_feeds_brd_rules_to_generation() -> None:
    prompt = system_prompt(
        GenerateRequest(
            description="Generate automated PCP quotation coverage.",
            generation_target="automation",
        )
    )

    assert "Quotation Services project profile" in prompt
    assert "BR-QT-018" in prompt
    assert "campaign contributions" in prompt
    assert "INVALID_TERM" in prompt
    assert "POST /api/v1/quotations" in prompt
    assert "average response is under one second" in prompt
    assert "P95 under two seconds" in prompt
    assert "## Input model" in prompt
    assert "## Output and error expectations" in prompt
    assert "approved golden quotation" in prompt
    assert "Product-specific calculation shape" in prompt
    assert "Quotation Services supported catalogue" in prompt
    assert "AUDI" in prompt
    assert "VWPC" in prompt
    assert "Mahindra" in prompt
    assert "`PCP`, `HP`, `LP`, `PCH`, `BCH`, `PFL`, `BFL`" in prompt
    assert "Maintenance codes are `S`, `SM`, and `SMT`" in prompt
    assert "targeted/non-targeted solver modes" in prompt
    assert "Avoid the full Cartesian product" in prompt


@pytest.mark.parametrize("target", ["manual", "automation"])
def test_auto_finance_generators_receive_every_brd_validation(target: str) -> None:
    prompt = system_prompt(
        GenerateRequest(
            description="Generate complete BRD quotation validation coverage.",
            generation_target=target,
        )
    )

    assert "## Mandatory validation inventory" in prompt
    for error_code in (
        "INVALID_BRAND",
        "INVALID_PRODUCT",
        "INVALID_CUSTOMER_TYPE",
        "INVALID_VEHICLE",
        "INVALID_VEHICLE_PRICE",
        "INVALID_DEPOSIT",
        "INVALID_TERM",
        "INVALID_MILEAGE",
        "INVALID_MAINTENANCE_OPTION",
        "PRODUCT_NOT_AVAILABLE_FOR_BRAND",
        "PRODUCT_NOT_AVAILABLE_FOR_CUSTOMER",
        "CAMPAIGN_NOT_APPLICABLE",
        "CAMPAIGN_EXPIRED",
        "INTEREST_RATE_NOT_AVAILABLE",
        "RESIDUAL_VALUE_NOT_AVAILABLE",
        "MAINTENANCE_RATE_NOT_AVAILABLE",
        "PRICING_CONFIGURATION_NOT_AVAILABLE",
        "INVALID_CALCULATION_INPUT",
        "CALCULATION_FAILED",
    ):
        assert error_code in prompt

    if target == "manual":
        assert "manually executable counterpart for every BRD validation" in prompt
    else:
        assert "every validation and all nineteen error codes" in prompt


def test_prompt_maps_requested_qa_labels_to_canonical_schema() -> None:
    prompt = system_prompt(
        GenerateRequest(
            description="Generate API cases with Requirement ID and HTTP Status fields.",
            generation_target="automation",
        ),
        profile="testpilot",
    )

    assert "Test Case ID to `id`" in prompt
    assert "HTTP Status to `tags`" in prompt
    assert "Never return a Markdown table" in prompt


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
