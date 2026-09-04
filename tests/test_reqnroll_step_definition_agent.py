import pytest

from app.agents.reqnroll_step_definition_agent import (
    ReqnRollStepDefinitionAgent,
    StepDefinitionRequest,
)
from app.agents.runner import CopilotAgentRunner, CopilotGenerationError
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


@pytest.mark.asyncio
async def test_step_definitions_fall_back_to_deterministic_reqnroll_bindings(
    monkeypatch,
) -> None:
    async def unavailable(*args, **kwargs):
        raise CopilotGenerationError("GitHub Copilot usage quota is exhausted.")

    monkeypatch.setattr(CopilotAgentRunner, "generate_structured", unavailable)
    agent = ReqnRollStepDefinitionAgent(Settings())
    request = StepDefinitionRequest(
        suite=_suite(
            gherkin=(
                "Scenario Outline: Quote\n"
                "  Given a <customerType> client\n"
                "  When it sends a quote\n"
                "  Then a quote is returned"
            )
        ),
        validation=_validation(True),
    )

    artifact = await agent.generate(request)

    assert artifact.files[0].path == "StepDefinitions/QuoteAPIStepDefinitions.cs"
    assert '[Given(@"^a (.+) client$")]' in artifact.files[0].content
    assert "string customerType" in artifact.files[0].content
    assert "NotImplementedException" in artifact.files[0].content
    assert len(artifact.coverage) == 3
    assert all(item.status == "generated" for item in artifact.coverage)
    assert "deterministic ReqnRoll bindings" in artifact.notes[0]


def test_fallback_reuses_binding_for_steps_that_only_differ_by_quoted_value() -> None:
    first = _suite(
        gherkin=(
            'Scenario: Retail quote\n  Given a "retail" customer\n'
            "  When a quote is requested\n  Then a quote is returned"
        )
    ).test_cases[0]
    second = first.model_copy(
        update={
            "id": "TC-002",
            "title": "Business quote",
            "gherkin": (
                'Scenario: Business quote\n  Given a "business" customer\n'
                "  When a quote is requested\n  Then a quote is returned"
            ),
        }
    )

    artifact = ReqnRollStepDefinitionAgent._fallback_artifact(
        "Quote API", [first, second]
    )

    content = artifact.files[0].content
    assert content.count("[Given(") == 1
    assert '[Given(@"^a ""([^""]+)"" customer$")]' in content
    given_coverage = [item for item in artifact.coverage if item.gherkin_step.startswith("Given")]
    assert [item.status for item in given_coverage] == ["generated", "reused"]
    assert given_coverage[0].binding == given_coverage[1].binding
