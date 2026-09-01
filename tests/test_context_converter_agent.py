import csv
import io
import json

import pytest
from openpyxl import load_workbook

from app.agents.context_converter_agent import ContextConversionError, ContextConverterAgent
from app.agents.test_case_validator import ValidationReport
from app.models import ExecutionMode, ExportFormat
from app.models import TestCase as Case
from app.models import TestCategory as Category
from app.models import TestDatum as Datum
from app.models import TestStep as Step
from app.models import TestSuite as Suite


def approved() -> ValidationReport:
    return ValidationReport(
        passed=True,
        score=100,
        acceptance_criteria_total=1,
        acceptance_criteria_covered=1,
    )


def suite() -> Suite:
    return Suite(
        feature_name="Account lockout",
        test_cases=[
            Case(
                id="TC-001",
                title="Lock after five failures",
                objective="Verify the account lockout business rule",
                category=Category.CRITICAL,
                priority="P0",
                execution_mode=ExecutionMode.MANUAL,
                feasibility_reason="A tester reviews the complete user experience",
                preconditions=["The account is active"],
                steps=[
                    Step(
                        action="Submit an invalid password five times",
                        expected_result="The account is locked after attempt five",
                    )
                ],
                test_data=[Datum(name="password", value="invalid", purpose="Fail sign-in")],
                tags=["security"],
                acceptance_criteria_covered=["BR-1"],
            )
        ],
    )


def test_converter_rejects_suite_that_failed_quality_gate() -> None:
    failed = approved().model_copy(update={"passed": False, "score": 80})

    with pytest.raises(ContextConversionError, match="quality-gate-approved"):
        ContextConverterAgent().convert(suite(), failed, ExportFormat.CSV)


def test_converter_creates_xray_csv_rows_per_step() -> None:
    artifact = ContextConverterAgent().convert(suite(), approved(), ExportFormat.CSV)
    rows = list(csv.DictReader(io.StringIO(artifact.content.decode("utf-8-sig"))))

    assert artifact.filename == "xray-test-cases.csv"
    assert rows[0]["Test Type"] == "Manual"
    assert rows[0]["Action"] == "Submit an invalid password five times"
    assert rows[0]["Requirements"] == "BR-1"


def test_converter_creates_excel_workbook() -> None:
    artifact = ContextConverterAgent().convert(suite(), approved(), ExportFormat.EXCEL)
    sheet = load_workbook(io.BytesIO(artifact.content)).active

    assert artifact.filename.endswith(".xlsx")
    assert sheet["A1"].value == "Test Case Identifier"
    assert sheet["B1"].value == "Scenario Group"
    assert sheet["I2"].value == "Submit an invalid password five times"


def test_converter_creates_xray_json_test_objects() -> None:
    artifact = ContextConverterAgent().convert(suite(), approved(), ExportFormat.JSON)
    tests = json.loads(artifact.content)

    assert tests[0]["testtype"] == "Manual"
    assert tests[0]["fields"]["summary"] == "Lock after five failures"
    assert tests[0]["steps"][0]["result"] == "The account is locked after attempt five"


def test_converter_creates_feature_with_scenario_outline_examples() -> None:
    automated = (
        suite()
        .test_cases[0]
        .model_copy(
            update={
                "execution_mode": ExecutionMode.AUTOMATION,
                "gherkin": """Scenario Outline: Lock account at the configured threshold
  Given an active account
  When invalid sign-in is attempted <attempts> times
  Then the account state is <state>

Examples:
  | attempts | state  |
  | 4        | active |
  | 5        | locked |""",
            }
        )
    )
    automated_suite = suite().model_copy(update={"test_cases": [automated]})

    artifact = ContextConverterAgent().convert(automated_suite, approved(), ExportFormat.FEATURE)
    content = artifact.content.decode()

    assert artifact.filename == "automation-tests.feature"
    assert content.startswith("Feature: Account lockout")
    assert "Scenario Outline:" in content
    assert "Examples:" in content


def test_feature_converter_rejects_outline_without_examples() -> None:
    automated = (
        suite()
        .test_cases[0]
        .model_copy(
            update={
                "execution_mode": ExecutionMode.AUTOMATION,
                "gherkin": "Scenario Outline: Incomplete parameterized scenario",
            }
        )
    )

    with pytest.raises(ContextConversionError, match="missing an Examples table"):
        ContextConverterAgent().convert(
            suite().model_copy(update={"test_cases": [automated]}),
            approved(),
            ExportFormat.FEATURE,
        )
