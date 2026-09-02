from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class TestCategory(StrEnum):
    CRITICAL = "critical"
    SMOKE = "smoke"
    SANITY = "sanity"
    REGRESSION = "regression"


class TestFormat(StrEnum):
    NORMAL = "normal"
    BDD = "bdd"


class ExecutionMode(StrEnum):
    AUTOMATION = "automation"
    MANUAL = "manual"


class GenerationTarget(StrEnum):
    """Specialist generation route requested by the caller."""

    AUTO = "auto"
    MANUAL = "manual"
    AUTOMATION = "automation"
    BOTH = "both"


class ManualTestingType(StrEnum):
    """Human-led test discipline requested for the manual specialist."""

    API = "api"
    UI = "ui"
    PERFORMANCE = "performance"
    DATABASE = "database"


class GenerationSource(StrEnum):
    COPILOT = "copilot"
    ORGANIZATIONAL_MEMORY = "organizational-memory"


class ExportFormat(StrEnum):
    CSV = "csv"
    EXCEL = "xlsx"
    JSON = "json"
    FEATURE = "feature"


class ManualArtifactFormat(StrEnum):
    CSV = "csv"
    EXCEL = "xlsx"


class ExecutionStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not-run"


class BusinessRule(BaseModel):
    id: str = Field(pattern=r"^BR-[A-Za-z0-9_-]+$")
    description: str = Field(min_length=3, max_length=2_000)


class TestStep(BaseModel):
    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)


class TestDatum(BaseModel):
    name: str
    value: str
    purpose: str


class TestCase(BaseModel):
    id: str = Field(description="Stable identifier such as TC-001")
    scenario_group: str = Field(
        default="General scenario",
        min_length=1,
        description="Business scenario that owns this test case and its shared coverage",
    )
    title: str
    objective: str
    category: TestCategory
    priority: str = Field(description="One of P0, P1, P2, P3")
    execution_mode: ExecutionMode
    feasibility_reason: str = Field(
        min_length=1,
        description="Why this scenario is suitable for automation or requires manual testing",
    )
    preconditions: list[str] = Field(default_factory=list)
    steps: list[TestStep] = Field(min_length=1)
    test_data: list[TestDatum] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    acceptance_criteria_covered: list[str] = Field(default_factory=list)
    gherkin: str | None = Field(
        default=None,
        description="Given/When/Then scenario when the requested format is BDD",
    )


class TestSuite(BaseModel):
    feature_name: str
    generation_source: GenerationSource = GenerationSource.COPILOT
    memory_key: str | None = None
    output_format: TestFormat = TestFormat.NORMAL
    assumptions: list[str] = Field(default_factory=list)
    coverage_notes: list[str] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(min_length=1)


class GenerateRequest(BaseModel):
    description: str = Field(min_length=10, max_length=30_000)
    additional_context: str = Field(default="", max_length=10_000)
    output_format: TestFormat = TestFormat.NORMAL
    generation_target: GenerationTarget = GenerationTarget.AUTO
    manual_testing_type: ManualTestingType = ManualTestingType.API
    business_rules: list[BusinessRule] = Field(default_factory=list, max_length=100)

    @field_validator("description")
    @classmethod
    def meaningful_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Description cannot be blank")
        return value.strip()


class ExpandRequest(BaseModel):
    request: GenerateRequest
    existing_titles: list[str] = Field(default_factory=list, max_length=100)


class JiraPublishRequest(BaseModel):
    issue_key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*-\d+$")
    suite: TestSuite
    selected_case_ids: list[str] = Field(min_length=1)
    add_comment: bool = True


class JiraPublishResult(BaseModel):
    issue_key: str
    attachment_name: str
    attachment_url: str | None = None
    comment_added: bool


class JiraRequirement(BaseModel):
    issue_key: str
    summary: str
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    source_fields: list[str] = Field(default_factory=list)

    @property
    def generation_description(self) -> str:
        sections = [f"Jira story {self.issue_key}: {self.summary}"]
        if self.description:
            sections.append(f"Description:\n{self.description}")
        if self.acceptance_criteria:
            criteria = "\n".join(
                f"AC-{index:03d}: {criterion}"
                for index, criterion in enumerate(self.acceptance_criteria, 1)
            )
            sections.append(f"Acceptance criteria:\n{criteria}")
        return "\n\n".join(sections)


class JiraGenerateRequest(BaseModel):
    issue_key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*-\d+$")
    output_format: TestFormat = TestFormat.NORMAL
    generation_target: GenerationTarget = GenerationTarget.AUTO
    manual_testing_type: ManualTestingType = ManualTestingType.API
    additional_context: str = Field(default="", max_length=10_000)


class DocumentSource(BaseModel):
    filename: str
    media_type: str
    extracted_characters: int = Field(ge=1)


class BusinessRuleDocumentResult(DocumentSource):
    business_rules: list[BusinessRule] = Field(min_length=1, max_length=100)


class SuiteRequest(BaseModel):
    suite: TestSuite


class AcceptSuiteRequest(SuiteRequest):
    validation: "ValidationReportPayload"
    selected_case_ids: list[str] = Field(min_length=1)
    manual_format: ManualArtifactFormat = ManualArtifactFormat.EXCEL
    accepted_by: str = Field(min_length=2, max_length=100)


class ValidationReportPayload(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    acceptance_criteria_total: int = Field(ge=0)
    acceptance_criteria_covered: int = Field(ge=0)
    findings: list[dict[str, object]] = Field(default_factory=list)


class AcceptedArtifact(BaseModel):
    filename: str
    format: str
    case_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    sha256: str


class AcceptanceReceipt(BaseModel):
    accepted_at: str
    accepted_by: str
    suite_hash: str
    selected_case_ids: list[str]
    output_directory: str
    artifacts: list[AcceptedArtifact]


class TestExecutionResult(BaseModel):
    case_id: str
    status: ExecutionStatus
    actual_result: str = Field(default="", max_length=5_000)
    duration_ms: int = Field(default=0, ge=0)


class ExecutionRequest(SuiteRequest):
    results: list[TestExecutionResult] = Field(min_length=1)


class ExecutionSummary(BaseModel):
    results: list[TestExecutionResult]
    total: int
    passed: int
    failed: int
    blocked: int
    not_run: int
    pass_rate: float


class DefectDraft(BaseModel):
    id: str
    title: str
    severity: str
    test_case_id: str
    expected_result: str
    actual_result: str
    requirement_mappings: list[str]
    status: str = "draft-review-required"


class MetricsReport(BaseModel):
    total_tests: int
    manual_tests: int
    automated_tests: int
    manual_coverage: float
    automation_coverage: float
    executed: int
    passed: int
    failed: int
    blocked: int
    pass_rate: float
    total_defects: int
    defect_density: float
