"""Keep the application validation decision explicit during code generation."""

from app.agent_instructions import load_agent_section
from app.agents.test_case_validator import ValidationReport, ValidationSeverity


def require_implementation_approval(report: ValidationReport) -> None:
    if not report.passed:
        raise ValueError("Step definitions require a Quality Gate-approved suite.")
    if any(finding.severity == ValidationSeverity.ERROR for finding in report.findings):
        raise ValueError(
            "The Quality Gate report is inconsistent: it says passed but contains errors. "
            "Correct the suite and run validation again before generating code."
        )


def implementation_approval_policy() -> str:
    return load_agent_section("quality-gate", "Implementation approval policy")


def implementation_approval_prompt(report: ValidationReport) -> str:
    require_implementation_approval(report)
    return "APPLICATION QUALITY GATE REPORT\n" + report.model_dump_json() + "\n\n"
