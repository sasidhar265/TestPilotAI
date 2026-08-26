import re
from enum import StrEnum

from pydantic import BaseModel, Field

from app.agents.roles import AgentKind, FunctionalAgentDescriptor
from app.models import GenerateRequest, TestCase, TestSuite


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class ValidationDimension(StrEnum):
    COVERAGE = "coverage"
    TRACEABILITY = "traceability"
    DUPLICATES = "duplicates"
    CLARITY = "clarity"
    EXPECTED_RESULTS = "expected-results"


class ValidationFinding(BaseModel):
    dimension: ValidationDimension
    severity: ValidationSeverity
    message: str
    test_case_ids: list[str] = Field(default_factory=list)
    acceptance_criterion: str | None = None


class ValidationReport(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    acceptance_criteria_total: int
    acceptance_criteria_covered: int
    findings: list[ValidationFinding] = Field(default_factory=list)


_AC_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?((?:AC[-_ ]?\d+)|(?:acceptance criterion\s*\d*))\s*[:.)-]\s*(.+)$",
    re.IGNORECASE,
)
_VAGUE = re.compile(
    r"\b(?:works?|correct(?:ly)?|appropriate(?:ly)?|proper(?:ly)?|successful(?:ly)?|"
    r"as expected|user-friendly|fast|quickly)\b",
    re.IGNORECASE,
)
_SPACE = re.compile(r"[^a-z0-9]+")


def _normal(value: str) -> str:
    return _SPACE.sub(" ", value.casefold()).strip()


def _criteria(description: str) -> list[str]:
    criteria: list[str] = []
    for line in description.splitlines():
        match = _AC_LINE.match(line)
        if match:
            label = match.group(1).strip()
            criteria.append(f"{label}: {match.group(2).strip()}")
    return criteria


def _same_scenario(left: TestCase, right: TestCase) -> bool:
    left_title, right_title = _normal(left.title), _normal(right.title)
    left_objective, right_objective = _normal(left.objective), _normal(right.objective)
    return (
        left_title == right_title
        or left_objective == right_objective
        or bool(left_title and right_title and set(left_title.split()) == set(right_title.split()))
    )


class TestCaseValidatorAgent:
    """Independent, deterministic quality gate for a generated test suite."""

    descriptor = FunctionalAgentDescriptor(
        id="test-case-validator-agent",
        name="Test Case Validator",
        kind=AgentKind.VALIDATOR,
        purpose="Independently assess generated test cases before they are stored or published.",
        runtime="local-deterministic",
        capabilities=("coverage", "traceability", "duplicates", "clarity", "expected-results"),
    )

    def validate(self, request: GenerateRequest, suite: TestSuite) -> ValidationReport:
        findings: list[ValidationFinding] = []
        criteria = _criteria(request.description)
        mappings: dict[str, set[str]] = {}

        for case in suite.test_cases:
            if not case.acceptance_criteria_covered:
                findings.append(
                    ValidationFinding(
                        dimension=ValidationDimension.TRACEABILITY,
                        severity=ValidationSeverity.WARNING,
                        message="Test case has no acceptance-criterion mapping.",
                        test_case_ids=[case.id],
                    )
                )
            for mapping in case.acceptance_criteria_covered:
                mappings.setdefault(_normal(mapping), set()).add(case.id)

            vague_fields = [
                name
                for name, value in (("title", case.title), ("objective", case.objective))
                if _VAGUE.search(value)
            ]
            if vague_fields:
                findings.append(
                    ValidationFinding(
                        dimension=ValidationDimension.CLARITY,
                        severity=ValidationSeverity.WARNING,
                        message=f"Vague wording found in {', '.join(vague_fields)}.",
                        test_case_ids=[case.id],
                    )
                )

            for index, step in enumerate(case.steps, start=1):
                expected = _normal(step.expected_result)
                if _VAGUE.search(step.expected_result) or expected == _normal(step.action):
                    findings.append(
                        ValidationFinding(
                            dimension=ValidationDimension.EXPECTED_RESULTS,
                            severity=ValidationSeverity.ERROR,
                            message=f"Step {index} needs a specific, observable expected result.",
                            test_case_ids=[case.id],
                        )
                    )

        for index, case in enumerate(suite.test_cases):
            for other in suite.test_cases[index + 1 :]:
                if _same_scenario(case, other):
                    findings.append(
                        ValidationFinding(
                            dimension=ValidationDimension.DUPLICATES,
                            severity=ValidationSeverity.ERROR,
                            message="Test cases appear to describe the same scenario.",
                            test_case_ids=[case.id, other.id],
                        )
                    )

        covered = 0
        for criterion in criteria:
            normalized = _normal(criterion)
            label = _normal(criterion.split(":", 1)[0])
            matched = any(
                key == normalized or key == label or key in normalized or normalized in key
                for key in mappings
            )
            if matched:
                covered += 1
            else:
                findings.append(
                    ValidationFinding(
                        dimension=ValidationDimension.COVERAGE,
                        severity=ValidationSeverity.ERROR,
                        message="Acceptance criterion is not covered by any test case.",
                        acceptance_criterion=criterion,
                    )
                )

        errors = sum(item.severity == ValidationSeverity.ERROR for item in findings)
        warnings = len(findings) - errors
        score = max(0, 100 - errors * 15 - warnings * 5)
        return ValidationReport(
            passed=errors == 0,
            score=score,
            acceptance_criteria_total=len(criteria),
            acceptance_criteria_covered=covered,
            findings=findings,
        )
