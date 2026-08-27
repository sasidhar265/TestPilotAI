from fastapi.testclient import TestClient

from app.agents.lifecycle_agents import (
    BugReporterAgent,
    BusinessRulesAgent,
    ExecutionAgent,
    MetricsAgent,
    TestDataAgent,
)
from app.main import app
from app.models import (
    BusinessRule,
    ExecutionMode,
    ExecutionRequest,
    ExecutionStatus,
    GenerateRequest,
)
from app.models import (
    TestCase as Case,
)
from app.models import (
    TestCategory as Category,
)
from app.models import (
    TestExecutionResult as Result,
)
from app.models import (
    TestStep as Step,
)
from app.models import (
    TestSuite as Suite,
)

client = TestClient(app)


def suite() -> Suite:
    return Suite(
        feature_name="Business rules",
        test_cases=[
            Case(
                id="TC-001",
                title="Apply quotation threshold",
                objective="Confirm the governing threshold",
                category=Category.CRITICAL,
                priority="P0",
                execution_mode=ExecutionMode.AUTOMATION,
                feasibility_reason="Deterministic threshold and observable result",
                steps=[Step(action="Submit quote", expected_result="Quote is accepted")],
                acceptance_criteria_covered=["BR-001"],
            ),
            Case(
                id="TC-002",
                title="Review quotation wording",
                objective="Confirm the wording is understandable",
                category=Category.REGRESSION,
                priority="P2",
                execution_mode=ExecutionMode.MANUAL,
                feasibility_reason="Requires human language judgment",
                steps=[Step(action="Review wording", expected_result="Wording is clear")],
            ),
        ],
    )


def execution_request() -> ExecutionRequest:
    return ExecutionRequest(
        suite=suite(),
        results=[
            Result(
                case_id="TC-001",
                status=ExecutionStatus.FAILED,
                actual_result="Quote was rejected",
                duration_ms=120,
            ),
            Result(case_id="TC-002", status=ExecutionStatus.PASSED),
        ],
    )


def test_business_rules_are_added_to_governing_generation_context() -> None:
    request = GenerateRequest(
        description="Generate quotation tests from the supplied requirement.",
        business_rules=[BusinessRule(id="BR-001", description="Quotes up to 5000 are accepted")],
    )

    enriched = BusinessRulesAgent().enrich(request)

    assert "BR-001: Quotes up to 5000 are accepted" in enriched.additional_context
    assert "acceptance_criteria_covered" in enriched.additional_context


def test_test_data_agent_fills_only_missing_synthetic_data() -> None:
    generated = TestDataAgent().generate(suite())

    assert generated.test_cases[0].test_data[0].name == "synthetic_reference"
    assert generated.test_cases[0].test_data[0].value == "qa_tc_001_001"


def test_execution_defect_and_metrics_agents_share_reviewed_evidence() -> None:
    request = execution_request()
    execution = ExecutionAgent().summarize(request)
    defects = BugReporterAgent().draft(request.suite, request.results)
    metrics = MetricsAgent().calculate(request.suite, execution, defects)

    assert execution.failed == 1
    assert execution.pass_rate == 50
    assert defects[0].test_case_id == "TC-001"
    assert defects[0].status == "draft-review-required"
    assert metrics.automation_coverage == 50
    assert metrics.manual_coverage == 50
    assert metrics.total_defects == 1
    assert metrics.defect_density == 0.5


def test_lifecycle_endpoints_operate_on_the_current_suite() -> None:
    request = execution_request()
    payload = request.model_dump(mode="json")

    execution_response = client.post("/api/execution", json=payload)
    defect_response = client.post("/api/defects", json=payload)
    metrics_response = client.post(
        "/api/metrics",
        json={
            "suite": payload["suite"],
            "execution": execution_response.json(),
            "defects": defect_response.json(),
        },
    )

    assert execution_response.status_code == 200
    assert defect_response.status_code == 200
    assert metrics_response.status_code == 200
    assert metrics_response.json()["total_defects"] == 1
