from app.agents.test_case_validator import (
    TestCaseValidatorAgent as Validator,
)
from app.agents.test_case_validator import (
    ValidationDimension,
)
from app.models import (
    ExecutionMode,
    GenerateRequest,
)
from app.models import (
    TestCase as Case,
)
from app.models import (
    TestCategory as Category,
)
from app.models import (
    TestStep as Step,
)
from app.models import (
    TestSuite as Suite,
)


def case(case_id: str, title: str, objective: str, criterion: str, expected: str) -> Case:
    return Case(
        id=case_id,
        title=title,
        objective=objective,
        category=Category.CRITICAL,
        priority="P0",
        execution_mode=ExecutionMode.AUTOMATION,
        feasibility_reason="The result is observable through a stable interface.",
        steps=[Step(action="submit the request", expected_result=expected)],
        acceptance_criteria_covered=[criterion] if criterion else [],
    )


def test_validator_passes_complete_traceable_suite() -> None:
    request = GenerateRequest(
        description="""Password reset requirements
AC-1: An expired link is rejected
AC-2: A valid link opens the reset form"""
    )
    suite = Suite(
        feature_name="Reset",
        test_cases=[
            case(
                "TC-001",
                "Reject expired reset link",
                "Verify expired link rejection",
                "AC-1",
                "An expired-link message is displayed",
            ),
            case(
                "TC-002",
                "Open valid reset link",
                "Verify the reset form opens",
                "AC-2",
                "The reset form is displayed",
            ),
        ],
    )

    report = Validator().validate(request, suite)

    assert report.passed
    assert report.score == 100
    assert report.acceptance_criteria_covered == 2


def test_validator_reports_uncovered_duplicate_vague_and_unobservable_results() -> None:
    request = GenerateRequest(
        description="""Password reset requirements
AC-1: An expired link is rejected
AC-2: A valid link opens the reset form"""
    )
    suite = Suite(
        feature_name="Reset",
        test_cases=[
            case(
                "TC-001",
                "Reset works correctly",
                "Verify reset works",
                "AC-1",
                "It works correctly",
            ),
            case("TC-002", "correctly works reset", "Verify reset works", "", "submit the request"),
        ],
    )

    report = Validator().validate(request, suite)
    dimensions = {finding.dimension for finding in report.findings}

    assert not report.passed
    assert report.acceptance_criteria_total == 2
    assert report.acceptance_criteria_covered == 1
    assert {
        ValidationDimension.COVERAGE,
        ValidationDimension.TRACEABILITY,
        ValidationDimension.DUPLICATES,
        ValidationDimension.CLARITY,
        ValidationDimension.EXPECTED_RESULTS,
    } <= dimensions


def test_free_form_requirements_still_check_case_traceability() -> None:
    request = GenerateRequest(description="Users need a secure password reset journey.")
    suite = Suite(
        feature_name="Reset",
        test_cases=[
            case(
                "TC-001", "Open reset form", "Verify reset form", "", "The reset form is displayed"
            ),
        ],
    )

    report = Validator().validate(request, suite)

    assert report.acceptance_criteria_total == 0
    assert any(item.dimension == ValidationDimension.TRACEABILITY for item in report.findings)
