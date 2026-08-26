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
