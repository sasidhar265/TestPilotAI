"""Convert quality-gate-approved suites into Xray/Jira interchange files."""

import csv
import io
import json
from dataclasses import dataclass

from openpyxl import Workbook

from app.agents.roles import AgentKind, FunctionalAgentDescriptor
from app.agents.test_case_validator import ValidationReport
from app.models import ExportFormat, TestSuite


class ContextConversionError(ValueError):
    """Raised when unapproved content reaches the conversion boundary."""


@dataclass(frozen=True)
class ConvertedArtifact:
    content: bytes
    filename: str
    media_type: str


class ContextConverterAgent:
    descriptor = FunctionalAgentDescriptor(
        id="context-converter-agent",
        name="Context Converter Agent",
        kind=AgentKind.CONTEXT_CONVERTER,
        purpose="Convert quality-gate-approved tests into Xray-ready CSV, Excel, or JSON.",
        runtime="local-deterministic",
        capabilities=(
            "xray-csv",
            "xray-excel",
            "xray-json",
            "gherkin-feature",
            "validated-input-only",
        ),
    )

    _HEADERS = (
        "Test Case Identifier",
        "Summary",
        "Test Type",
        "Priority",
        "Description",
        "Preconditions",
        "Step",
        "Action",
        "Test Data",
        "Expected Result",
        "Labels",
        "Requirements",
    )

    def convert(
        self, suite: TestSuite, validation: ValidationReport, output_format: ExportFormat
    ) -> ConvertedArtifact:
        if not validation.passed:
            raise ContextConversionError("Only a quality-gate-approved suite can be converted.")
        if output_format == ExportFormat.CSV:
            content = self._csv(suite)
            return ConvertedArtifact(content, "xray-test-cases.csv", "text/csv")
        if output_format == ExportFormat.EXCEL:
            content = self._excel(suite)
            return ConvertedArtifact(
                content,
                "xray-test-cases.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        if output_format == ExportFormat.FEATURE:
            content = self._feature(suite)
            return ConvertedArtifact(content, "automation-tests.feature", "text/x-gherkin")
        content = self._json(suite)
        return ConvertedArtifact(content, "xray-test-cases.json", "application/json")

    def _rows(self, suite: TestSuite) -> list[list[str | int]]:
        rows: list[list[str | int]] = []
        for case in suite.test_cases:
            data = "\n".join(f"{item.name}={item.value}" for item in case.test_data)
            for step_number, step in enumerate(case.steps, 1):
                rows.append(
                    [
                        case.id,
                        case.title,
                        "Manual" if case.execution_mode.value == "manual" else "Generic",
                        case.priority,
                        case.objective,
                        "\n".join(case.preconditions),
                        step_number,
                        step.action,
                        data,
                        step.expected_result,
                        ",".join(case.tags),
                        ",".join(case.acceptance_criteria_covered),
                    ]
                )
        return rows

    def _csv(self, suite: TestSuite) -> bytes:
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(self._HEADERS)
        writer.writerows(self._rows(suite))
        return output.getvalue().encode("utf-8-sig")

    def _excel(self, suite: TestSuite) -> bytes:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Xray Tests"
        sheet.append(self._HEADERS)
        for row in self._rows(suite):
            sheet.append(row)
        sheet.freeze_panes = "A2"
        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue()

    def _json(self, suite: TestSuite) -> bytes:
        tests = []
        for case in suite.test_cases:
            tests.append(
                {
                    "testtype": "Manual" if case.execution_mode.value == "manual" else "Generic",
                    "fields": {
                        "summary": case.title,
                        "description": case.objective,
                        "priority": {"name": case.priority},
                        "labels": case.tags,
                    },
                    "steps": [
                        {
                            "action": step.action,
                            "data": "\n".join(
                                f"{item.name}={item.value}" for item in case.test_data
                            ),
                            "result": step.expected_result,
                        }
                        for step in case.steps
                    ],
                    "requirements": case.acceptance_criteria_covered,
                }
            )
        return json.dumps(tests, indent=2, ensure_ascii=False).encode("utf-8")

    def _feature(self, suite: TestSuite) -> bytes:
        scenarios: list[str] = []
        for case in suite.test_cases:
            if case.execution_mode.value != "automation":
                continue
            scenario = (case.gherkin or "").strip()
            if not scenario.startswith(("Scenario:", "Scenario Outline:")):
                lines = [f"Scenario: {case.title}"]
                if case.preconditions:
                    lines.extend(
                        f"  {'Given' if index == 0 else 'And'} {condition}"
                        for index, condition in enumerate(case.preconditions)
                    )
                else:
                    lines.append("  Given the feature preconditions are satisfied")
                for index, step in enumerate(case.steps):
                    lines.append(f"  {'When' if index == 0 else 'And'} {step.action}")
                    lines.append(f"  {'Then' if index == 0 else 'And'} {step.expected_result}")
                scenario = "\n".join(lines)
            if scenario.startswith("Scenario Outline:") and "Examples:" not in scenario:
                raise ContextConversionError(
                    f"Automation scenario outline {case.id} is missing an Examples table."
                )
            scenarios.append(scenario)
        if not scenarios:
            raise ContextConversionError("The approved suite contains no automation scenarios.")
        feature = f"Feature: {suite.feature_name}\n\n" + "\n\n".join(scenarios) + "\n"
        return feature.encode("utf-8")
