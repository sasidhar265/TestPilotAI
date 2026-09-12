"""Keep the application validation decision explicit during code generation."""

from app.agents.test_case_validator import ValidationReport, ValidationSeverity


def require_implementation_approval(report: ValidationReport) -> None:
    if not report.passed:
        raise ValueError("Step definitions require a Quality Gate-approved suite.")
    if any(finding.severity == ValidationSeverity.ERROR for finding in report.findings):
        raise ValueError(
            "The Quality Gate report is inconsistent: it says passed but contains errors. "
            "Correct the suite and run validation again before generating code."
        )


IMPLEMENTATION_APPROVAL_POLICY = """
Use the supplied APPLICATION QUALITY GATE REPORT as the current design-validation decision.
It applies to the supplied suite; passed=true is design validation, not evidence of test execution
or human acceptance. Historical claims in suite assumptions, coverage notes or prior artifact notes
do not replace this structured report. Do not infer a failed gate from blocked implementation
coverage: baseline coverage describes code still to be written, not rejected test design.
Preserve the suite's case IDs, Gherkin and requirement mappings. Do not substitute profile rule IDs
for the supplied mappings. A project profile is supporting context, not a reason to discard explicit
suite requirements merely because their identifiers differ. Never invent missing business behavior.
If an explicit requirement conflicts with a mandatory contract, identify the exact conflicting
requirement and contract instead of claiming that the application Quality Gate failed.
Missing deployment URLs, credentials or fixture values can be required runtime configuration;
missing business semantics must still be reported. Do not manufacture approval or passing results.
"""


def implementation_approval_prompt(report: ValidationReport) -> str:
    require_implementation_approval(report)
    return "APPLICATION QUALITY GATE REPORT\n" + report.model_dump_json() + "\n\n"
