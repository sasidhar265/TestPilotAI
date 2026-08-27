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


class GenerationSource(StrEnum):
    COPILOT = "copilot"
    ORGANIZATIONAL_MEMORY = "organizational-memory"


class ExportFormat(StrEnum):
    CSV = "csv"
    EXCEL = "xlsx"
    JSON = "json"
    FEATURE = "feature"


class TestStep(BaseModel):
    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)


class TestDatum(BaseModel):
    name: str
    value: str
    purpose: str


class TestCase(BaseModel):
    id: str = Field(description="Stable identifier such as TC-001")
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


class DocumentSource(BaseModel):
    filename: str
    media_type: str
    extracted_characters: int = Field(ge=1)
