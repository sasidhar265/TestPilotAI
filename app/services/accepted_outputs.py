"""Persist explicitly accepted, quality-gate-approved test-design artifacts."""

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from app.agents.context_converter_agent import ContextConverterAgent
from app.agents.test_case_validator import TestCaseValidatorAgent, ValidationReport
from app.models import (
    AcceptanceReceipt,
    AcceptedArtifact,
    AcceptSuiteRequest,
    ExecutionMode,
    ExportFormat,
    GenerateRequest,
    ManualArtifactFormat,
)

_SAFE_NAME = re.compile(r"[^a-z0-9]+")


class AcceptanceError(ValueError):
    """Raised when a suite cannot cross the explicit acceptance boundary."""


class AcceptedOutputService:
    def __init__(self, output_directory: Path) -> None:
        self.output_directory = output_directory
        self.converter = ContextConverterAgent()

    def accept(self, request: AcceptSuiteRequest) -> AcceptanceReceipt:
        if not request.validation.passed:
            raise AcceptanceError("Only a passing quality-gate suite can be accepted.")
        selected_ids = set(request.selected_case_ids)
        selected = [case for case in request.suite.test_cases if case.id in selected_ids]
        missing = selected_ids - {case.id for case in selected}
        if missing:
            raise AcceptanceError(f"Unknown selected test case IDs: {', '.join(sorted(missing))}")
        if not selected:
            raise AcceptanceError("Select at least one test case for acceptance.")

        selected_suite = request.suite.model_copy(update={"test_cases": selected})
        structural_request = GenerateRequest(
            description=f"Accepted test suite for {request.suite.feature_name}.",
            output_format=request.suite.output_format,
        )
        if not TestCaseValidatorAgent().validate(structural_request, selected_suite).passed:
            raise AcceptanceError(
                "Selected cases no longer pass server-side structural validation."
            )

        self.output_directory.mkdir(parents=True, exist_ok=True)
        self._restrict_permissions(self.output_directory, 0o700)
        timestamp = datetime.now(UTC)
        stem = self._stem(request.suite.feature_name, timestamp)
        validation = ValidationReport.model_validate(request.validation.model_dump())
        artifacts: list[AcceptedArtifact] = []

        manual_cases = [case for case in selected if case.execution_mode == ExecutionMode.MANUAL]
        if manual_cases:
            manual_suite = request.suite.model_copy(update={"test_cases": manual_cases})
            export_format = (
                ExportFormat.CSV
                if request.manual_format == ManualArtifactFormat.CSV
                else ExportFormat.EXCEL
            )
            converted = self.converter.convert(manual_suite, validation, export_format)
            suffix = "csv" if export_format == ExportFormat.CSV else "xlsx"
            artifacts.append(
                self._store(
                    f"{stem}-manual-tests.{suffix}",
                    suffix,
                    len(manual_cases),
                    converted.content,
                )
            )

        automation_cases = [
            case for case in selected if case.execution_mode == ExecutionMode.AUTOMATION
        ]
        if automation_cases:
            automation_suite = request.suite.model_copy(update={"test_cases": automation_cases})
            converted = self.converter.convert(automation_suite, validation, ExportFormat.FEATURE)
            artifacts.append(
                self._store(
                    f"{stem}-automation-tests.feature",
                    "feature",
                    len(automation_cases),
                    converted.content,
                )
            )

        suite_hash = hashlib.sha256(request.suite.model_dump_json().encode("utf-8")).hexdigest()
        receipt = AcceptanceReceipt(
            accepted_at=timestamp.isoformat(),
            accepted_by=request.accepted_by.strip(),
            suite_hash=suite_hash,
            selected_case_ids=[case.id for case in selected],
            output_directory=str(self.output_directory),
            artifacts=artifacts,
        )
        receipt_content = json.dumps(receipt.model_dump(mode="json"), indent=2).encode("utf-8")
        self._store(f"{stem}-acceptance.json", "acceptance", len(selected), receipt_content)
        return receipt

    def _store(
        self, filename: str, format_name: str, count: int, content: bytes
    ) -> AcceptedArtifact:
        destination = self.output_directory / filename
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(content)
        self._restrict_permissions(temporary, 0o600)
        os.replace(temporary, destination)
        return AcceptedArtifact(
            filename=filename,
            format=format_name,
            case_count=count,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    @staticmethod
    def _stem(feature_name: str, timestamp: datetime) -> str:
        slug = _SAFE_NAME.sub("-", feature_name.casefold()).strip("-")[:60] or "test-suite"
        return f"{timestamp:%Y%m%dT%H%M%S%fZ}-{slug}"

    @staticmethod
    def _restrict_permissions(path: Path, mode: int) -> None:
        try:
            os.chmod(path, mode)
        except OSError:
            pass
