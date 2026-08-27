from app.agents.context_converter_agent import ContextConverterAgent
from app.agents.output_agent import OutputAgent
from app.agents.test_case_validator import ValidationReport
from app.models import ExecutionMode, ExportFormat, GenerateRequest
from app.models import TestCase as Case
from app.models import TestCategory as Category
from app.models import TestStep as Step
from app.models import TestSuite as Suite


def suite() -> Suite:
    return Suite(
        feature_name="Account lockout",
        test_cases=[
            Case(
                id="TC-001",
                title="Lock account after five failed sign-ins",
                objective="Verify the security lockout threshold",
                category=Category.CRITICAL,
                priority="P0",
                execution_mode=ExecutionMode.MANUAL,
                feasibility_reason="Requires human review",
                steps=[Step(action="Fail sign-in five times", expected_result="Account is locked")],
                acceptance_criteria_covered=["BR-1"],
            )
        ],
    )


def test_output_agent_stores_converted_artifact_and_retrieves_knowledge(tmp_path) -> None:
    validation = ValidationReport(
        passed=True,
        score=100,
        acceptance_criteria_total=1,
        acceptance_criteria_covered=1,
    )
    artifact = ContextConverterAgent().convert(suite(), validation, ExportFormat.JSON)
    agent = OutputAgent(tmp_path / "knowledge.db")

    artifact_id = agent.store(suite(), ExportFormat.JSON, artifact)
    knowledge = agent.knowledge_for(
        GenerateRequest(description="Review the account lockout security threshold")
    )

    assert artifact_id is not None
    assert agent.count() == 1
    assert "APPROVED ORGANIZATIONAL KNOWLEDGE" in knowledge
    assert "Lock account after five failed sign-ins" in knowledge


def test_output_agent_deduplicates_identical_artifacts(tmp_path) -> None:
    validation = ValidationReport(
        passed=True,
        score=100,
        acceptance_criteria_total=0,
        acceptance_criteria_covered=0,
    )
    artifact = ContextConverterAgent().convert(suite(), validation, ExportFormat.CSV)
    agent = OutputAgent(tmp_path / "knowledge.db")

    agent.store(suite(), ExportFormat.CSV, artifact)
    agent.store(suite(), ExportFormat.CSV, artifact)

    assert agent.count() == 1
    assert agent.scenario_count() == 1


def test_output_agent_stores_feature_file_and_individual_scenario(tmp_path) -> None:
    automated = (
        suite()
        .test_cases[0]
        .model_copy(
            update={
                "execution_mode": ExecutionMode.AUTOMATION,
                "gherkin": """Scenario Outline: Lock at threshold
  When sign-in fails <attempts> times
  Then the account is <state>

Examples:
  | attempts | state  |
  | 5        | locked |""",
            }
        )
    )
    feature_suite = suite().model_copy(update={"test_cases": [automated]})
    validation = ValidationReport(
        passed=True,
        score=100,
        acceptance_criteria_total=1,
        acceptance_criteria_covered=1,
    )
    artifact = ContextConverterAgent().convert(feature_suite, validation, ExportFormat.FEATURE)
    agent = OutputAgent(tmp_path / "knowledge.db")

    artifact_id = agent.store(feature_suite, ExportFormat.FEATURE, artifact)

    assert artifact_id is not None
    assert agent.count() == 1
    assert agent.scenario_count() == 1
