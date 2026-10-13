from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.models import (
    AcceptSuiteRequest,
    ExecutionMode,
)
from app.models import TestCase as Case
from app.models import TestCategory as Category
from app.models import TestStep as Step
from app.models import TestSuite as Suite
from app.services.accepted_outputs import AcceptanceError, AcceptedOutputService


def approved_suite() -> Suite:
    return Suite(
        feature_name="Account access",
        output_format="bdd",
        test_cases=[
            Case(
                id="TC-001",
                title="Review account recovery wording",
                objective="Confirm recovery guidance is understandable",
                category=Category.REGRESSION,
                priority="P2",
                execution_mode=ExecutionMode.MANUAL,
                feasibility_reason="Requires human language judgment",
                steps=[
                    Step(
                        action="Review the recovery message",
                        expected_result="The guidance names the next recovery action",
                    )
                ],
            ),
            Case(
                id="TC-002",
                title="Recover an account",
                objective="Confirm a registered user can recover access",
                category=Category.CRITICAL,
                priority="P0",
                execution_mode=ExecutionMode.AUTOMATION,
                feasibility_reason="Stable workflow with observable account state",
                steps=[
                    Step(
                        action="Submit a valid recovery token",
                        expected_result="The account recovery form is displayed",
                    )
                ],
                gherkin=(
                    "Scenario: Recover an account\n"
                    "  Given a registered account\n"
                    "  When a valid recovery token is submitted\n"
                    "  Then the account recovery form is displayed"
                ),
            ),
        ],
    )


def acceptance_request(manual_format: str = "xlsx") -> AcceptSuiteRequest:
    return AcceptSuiteRequest(
        suite=approved_suite(),
        validation={
            "passed": True,
            "score": 100,
            "acceptance_criteria_total": 0,
            "acceptance_criteria_covered": 0,
            "findings": [],
        },
        selected_case_ids=["TC-001", "TC-002"],
        manual_format=manual_format,
        accepted_by="qa-reviewer@example.test",
    )


def test_acceptance_stores_excel_feature_and_receipt(tmp_path: Path) -> None:
    receipt = AcceptedOutputService(tmp_path).accept(acceptance_request())

    assert receipt.accepted_by == "qa-reviewer@example.test"
    assert receipt.selected_case_ids == ["TC-001", "TC-002"]
    assert {artifact.format for artifact in receipt.artifacts} == {"xlsx", "feature"}
    assert len(list(tmp_path.glob("*-acceptance.json"))) == 1
    feature = next(tmp_path.glob("*-automation-tests.feature"))
    assert "Feature: Account access" in feature.read_text(encoding="utf-8")
    workbook = load_workbook(next(tmp_path.glob("*-manual-tests.xlsx")), read_only=True)
    try:
        assert workbook.active["A2"].value == "TC-001"
    finally:
        workbook.close()


def test_acceptance_can_store_manual_cases_as_csv(tmp_path: Path) -> None:
    request = acceptance_request("csv").model_copy(update={"selected_case_ids": ["TC-001"]})

    receipt = AcceptedOutputService(tmp_path).accept(request)

    assert [artifact.format for artifact in receipt.artifacts] == ["csv"]
    assert "TC-001" in next(tmp_path.glob("*-manual-tests.csv")).read_text(encoding="utf-8-sig")
    assert not list(tmp_path.glob("*.feature"))


def test_acceptance_rejects_failed_validation_and_unknown_case(tmp_path: Path) -> None:
    failed = acceptance_request().model_copy(
        update={"validation": acceptance_request().validation.model_copy(update={"passed": False})}
    )
    unknown = acceptance_request().model_copy(update={"selected_case_ids": ["TC-404"]})

    with pytest.raises(AcceptanceError, match="passing quality-gate"):
        AcceptedOutputService(tmp_path).accept(failed)
    with pytest.raises(AcceptanceError, match="Unknown selected"):
        AcceptedOutputService(tmp_path).accept(unknown)


def test_saved_approvals_discoverable_without_reuse_and_preserve_selected_suite(tmp_path):
    service = AcceptedOutputService(tmp_path)
    request = acceptance_request().model_copy(update={"selected_case_ids": ["TC-001"]})
    receipt = service.accept(request)
    inventory = service.inventory()
    assert len(inventory) == 1
    assert inventory[0]["accepted_by"] == receipt.accepted_by
    detail = service.entry(inventory[0]["artifact_id"])
    assert [case["id"] for case in detail["suite"]["test_cases"]] == ["TC-001"]
    assert detail["acceptance"]["selected_case_ids"] == ["TC-001"]


def test_existing_receipts_work_without_suite_snapshot_and_reject_modified_files(tmp_path):
    service = AcceptedOutputService(tmp_path)
    service.accept(acceptance_request("csv"))
    next(tmp_path.glob("*-suite.json")).unlink()
    assert len(service.inventory()) == 2
    path = next(tmp_path.glob("*.feature"))
    path.write_text("Modified after approval")
    assert len(service.inventory()) == 1


def test_acceptance_preserves_grounded_story_and_scenario_approval_evidence(tmp_path):
    import json

    context = json.loads(Path("automation/Input/Workflow.Json").read_text())["approved-scenarios"][
        "body"
    ]
    context["story_approvals"] = {"ST-001": "Reviewer"}
    context["scenario_approvals"] = {"SC-001": "Reviewer"}
    request = acceptance_request().model_copy(update={"workflow_context": context})
    service = AcceptedOutputService(tmp_path)
    service.accept(request)
    detail = service.entry(service.inventory()[0]["artifact_id"])
    assert detail["workflow"]["story_approvals"] == {"ST-001": "Reviewer"}
    invalid = context | {"story_approvals": {"ST-404": "Reviewer"}}
    with pytest.raises(AcceptanceError, match="Unknown stage approval"):
        service.accept(request.model_copy(update={"workflow_context": invalid}))
