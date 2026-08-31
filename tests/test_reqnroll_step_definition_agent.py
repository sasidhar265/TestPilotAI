import pytest

from app.agents.reqnroll_step_definition_agent import (
    ReqnRollStepDefinitionAgent,
    StepDefinitionRequest,
)
from app.agents.test_case_validator import ValidationReport
from app.config import Settings
from app.models import TestCase as Case
from app.models import TestStep as Step
from app.models import TestSuite as Suite


def _suite(mode: str = "automation", gherkin: str | None = None) -> Suite:
    return Suite(
        feature_name="Quote API",
        output_format="bdd",
        test_cases=[
            Case(
                id="TC-001",
                title="Create quote",
                objective="Create a valid quote",
                category="smoke",
                priority="P1",
                execution_mode=mode,
                feasibility_reason="Stable API",
                steps=[Step(action="Send request", expected_result="Quote is returned")],
                gherkin=gherkin,
            )
        ],
    )


def _validation(passed: bool) -> ValidationReport:
    return ValidationReport(
        passed=passed,
        score=100 if passed else 50,
        acceptance_criteria_total=0,
        acceptance_criteria_covered=0,
    )


@pytest.mark.asyncio
async def test_step_definitions_require_quality_gate_approval() -> None:
    agent = ReqnRollStepDefinitionAgent(Settings())
    request = StepDefinitionRequest(
        suite=_suite(
            gherkin=(
                "Scenario: Quote\n  Given a client\n  When it sends a quote\n"
                "  Then a quote is returned"
            )
        ),
        validation=_validation(False),
    )

    with pytest.raises(ValueError, match="Quality Gate-approved"):
        await agent.generate(request)


@pytest.mark.asyncio
async def test_step_definitions_require_automation_gherkin() -> None:
    agent = ReqnRollStepDefinitionAgent(Settings())
    request = StepDefinitionRequest(suite=_suite(mode="manual"), validation=_validation(True))

    with pytest.raises(ValueError, match="no automation Gherkin"):
        await agent.generate(request)
