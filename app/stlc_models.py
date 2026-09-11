"""Validated inputs for versioned requirements and evidence-based execution."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models import TestSuite

Text = Annotated[str, Field(min_length=1, max_length=4000)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")]


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RequirementInput(Input):
    project: Identifier = "default"
    key: Identifier
    title: Text
    description: Text
    acceptance_criteria: list[Text] = Field(default_factory=list, max_length=100)
    owner: Text
    source: Text
    expected_version: int = Field(default=0, ge=0)
    change_reason: Text


class ReviewInput(Input):
    action: Literal["submit", "approve", "reject", "comment"]
    comment: Text


class BaselineInput(Input):
    project: Identifier = "default"
    name: Text
    requirement_ids: list[Identifier] = Field(min_length=1, max_length=100)


class SuiteVersionInput(Input):
    baseline_id: Identifier
    suite: TestSuite
    mappings: dict[str, list[str]]


class CycleInput(Input):
    suite_id: Identifier
    name: Text
    build: Text
    environment: Text
    assignments: dict[str, Text]


class StepEvidence(Input):
    step: int = Field(ge=1)
    status: Literal["passed", "failed", "blocked", "not-run"]
    actual: Text


class AttemptInput(Input):
    case_id: Identifier
    status: Literal["passed", "failed", "blocked", "not-run"]
    actual: Text
    evidence: list[HttpUrl] = Field(default_factory=list, max_length=20)
    steps: list[StepEvidence] = Field(default_factory=list, max_length=200)
    duration_ms: int = Field(default=0, ge=0)
    retest_of: Identifier | None = None


class ImportInput(Input):
    run_key: Identifier
    build: Text
    environment: Text
    results: list[AttemptInput] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_cases(self) -> "ImportInput":
        if len({item.case_id for item in self.results}) != len(self.results):
            raise ValueError(
                "Import must contain one result per case; aggregate outline rows first"
            )
        return self


class DefectInput(Input):
    attempt_id: Identifier
    title: Text
    severity: Literal["critical", "major", "minor"]


class DefectUpdate(Input):
    status: Literal["open", "in-progress", "resolved", "closed", "reopened"]
    comment: Text
    jira_key: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]*-[1-9][0-9]*$")] | None = None


class PackInput(Input):
    files: dict[str, str] = Field(min_length=1, max_length=100)
    project_path: Text
    test_mappings: dict[str, Identifier] = Field(min_length=1, max_length=1000)
    review_comment: Text


class JiraDefectInput(Input):
    project_key: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{1,49}$")]
