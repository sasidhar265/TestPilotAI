from app.generator import finalize_suite
from app.models import ExecutionMode, GenerateRequest
from app.models import TestCase as Case
from app.models import TestCategory as Category
from app.models import TestStep as Step
from app.models import TestSuite as Suite


def case(case_id: str) -> Case:
    return Case(
        id=case_id,
        title="Reset an expired link",
        objective="Reject an expired link",
        category=Category.CRITICAL,
        priority="P0",
        execution_mode=ExecutionMode.AUTOMATION,
        feasibility_reason="Deterministic link state and observable rejection message",
        preconditions=["a reset link was issued more than 15 minutes ago"],
        steps=[
            Step(
                action="the customer opens the reset link",
                expected_result="the link is rejected as expired",
            )
        ],
    )


def test_quality_gate_enforces_bdd_and_removes_duplicates() -> None:
    suite = Suite(
        feature_name="Password reset",
        test_cases=[case("TC-001"), case("TC-002")],
    )
    request = GenerateRequest(
        description="As a customer, I want a reset link that expires after 15 minutes.",
        output_format="bdd",
    )

    result = finalize_suite(suite, request)

    assert result.output_format == "bdd"
    assert len(result.test_cases) == 1
    assert "Given a reset link was issued more than 15 minutes ago" in result.test_cases[0].gherkin
    assert "Then the link is rejected as expired" in result.test_cases[0].gherkin


def test_quality_gate_preserves_specflow_scenario_outline() -> None:
    outline = case("TC-001").model_copy(
        update={
            "gherkin": """Scenario Outline: Reject invalid reset links
  Given a reset link is <state>
  When the customer opens the reset link
  Then the link is rejected with <message>

Examples:
  | state   | message        |
  | expired | Link expired   |
  | used    | Link used      |"""
        }
    )
    suite = Suite(feature_name="Password reset", test_cases=[outline])
    request = GenerateRequest(
        description="As a customer, I want invalid reset links rejected.",
        output_format="bdd",
    )

    result = finalize_suite(suite, request)

    assert result.test_cases[0].gherkin == outline.gherkin
    assert "Scenario Outline:" in result.test_cases[0].gherkin
    assert "Examples:" in result.test_cases[0].gherkin


def test_generated_gherkin_compacts_multiple_structured_steps_to_given_when_then() -> None:
    multi_step = case("TC-001").model_copy(
        update={
            "preconditions": ["an authenticated consumer", "a valid PCP product"],
            "steps": [
                Step(action="submit a quote", expected_result="a quote ID is returned"),
                Step(action="retrieve the quote", expected_result="the same quote is returned"),
            ],
        }
    )

    result = finalize_suite(
        Suite(feature_name="Quotation", test_cases=[multi_step]),
        GenerateRequest(description="Generate a valid quotation scenario.", output_format="bdd"),
    )
    steps = [
        line.strip()
        for line in result.test_cases[0].gherkin.splitlines()
        if line.strip().startswith(("Given ", "When ", "Then ", "And ", "But "))
    ]

    assert len(steps) == 3
    assert [line.split(maxsplit=1)[0] for line in steps] == ["Given", "When", "Then"]


def test_generated_gherkin_keeps_each_step_text_within_100_characters() -> None:
    long_case = case("TC-001").model_copy(
        update={
            "preconditions": ["an authenticated consumer " + "with valid permissions " * 8],
            "steps": [
                Step(
                    action="submit a quotation request " + "with detailed finance inputs " * 8,
                    expected_result="a generated quotation is returned "
                    + "with all calculated finance values " * 8,
                )
            ],
        }
    )

    result = finalize_suite(
        Suite(feature_name="Quotation", test_cases=[long_case]),
        GenerateRequest(description="Generate a quotation.", output_format="bdd"),
    )

    for line in result.test_cases[0].gherkin.splitlines()[1:]:
        assert len(line.strip().split(maxsplit=1)[1]) <= 100
