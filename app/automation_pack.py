"""Deterministic framework assets derived from the current approved suite."""

import json
from pathlib import Path

from app.agents.context_converter_agent import ContextConverterAgent
from app.agents.reqnroll_implementations import approved_fixture_json
from app.automation_layout import folder_notes
from app.models import ExecutionMode, TestSuite
from app.quotation_contract import PAYLOAD_PATH

TEMPLATES = Path(__file__).parent / "templates" / "framework"


def shared_assets(suite: TestSuite) -> dict[str, str]:
    cases = [case for case in suite.test_cases if case.execution_mode == ExecutionMode.AUTOMATION]
    return {
        **folder_notes(),
        "Input/TestData.Json": approved_fixture_json(cases),
        "Input/QuotationRequest.Json": PAYLOAD_PATH.read_text(),
        "Input/CaseData.Json": json.dumps(
            {case.id: [datum.model_dump() for datum in case.test_data] for case in cases},
            ensure_ascii=False,
            indent=2,
        ),
        "Features/generated.feature": ContextConverterAgent()._feature(suite).decode(),
    }


def csharp_assets(suite: TestSuite, notes: list[str]) -> dict[str, str]:
    return {
        **shared_assets(suite),
        "Automation.csproj": (TEMPLATES / "Automation.csproj").read_text(),
        "Reqnroll/Automation.runsettings": (TEMPLATES / "Automation.runsettings").read_text(),
        "Hooks/Hooks.cs": (TEMPLATES / "Hooks.cs").read_text(),
        "README.md": (
            "# Automation Framework\n\n"
            "Requires .NET 8+. Review generated code and configure the target environment.\n"
            "Run `dotnet test Automation.csproj --results-directory TestResults/Reports`.\n"
            "The project automatically loads Features, StepDefinitions and Hooks and copies "
            "Input/TestData.Json to the output directory. Reqnroll owns scenario-scoped "
            "context disposal. Reports are produced only on execution.\n\n"
            "Input/TestData.Json contains unambiguous approved JSON fixtures by name. "
            "Set API_FIXTURE_FILE to override it. Missing data fails explicitly.\n\n"
            "Quotation requests use Input/QuotationRequest.Json exactly as supplied. "
            "Use QuotationRequestBuilder.FromFile(path).WithDeposit(value).WithTerm(term).Build() "
            "for explicit approved overrides. The step 'Given the approved quotation request' "
            "loads the default through ApprovedQuotationRequestStrategy. Named quotation "
            "fixtures must have the same complete wire shape; unknown fields fail validation. "
            "ConfiguredQuotationRequestStrategy accepts typed builder overrides. "
            "Do not add request fields from older BRD examples.\n\n"
            + "\n\n".join(note for note in notes if not note.startswith("Reused validated C#"))
        ),
    }
