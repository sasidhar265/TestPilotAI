import pytest

from app.agents.reqnroll_step_definition_agent import (
    ReqnRollStepDefinitionAgent,
    StepDefinitionRequest,
)
from app.agents.runner import CopilotAgentRunner, CopilotGenerationError
from app.agents.test_case_validator import ValidationReport
from app.config import Settings
from app.models import TestCase as Case
from app.models import TestStep as Step
from app.models import TestSuite as Suite


def _suite(mode: str = "automation", gherkin: str | None = None) -> Suite:
    return Suite(
        feature_name="Quote API",
        output_format="bdd",
        test_cases=[
            Case(
                id="TC-001",
                title="Create quote",
                objective="Create a valid quote",
                category="smoke",
                priority="P1",
                execution_mode=mode,
                feasibility_reason="Stable API",
                steps=[Step(action="Send request", expected_result="Quote is returned")],
                gherkin=gherkin,
            )
        ],
    )


def _validation(passed: bool) -> ValidationReport:
    return ValidationReport(
        passed=passed,
        score=100 if passed else 50,
        acceptance_criteria_total=0,
        acceptance_criteria_covered=0,
    )


@pytest.mark.asyncio
async def test_step_definitions_require_quality_gate_approval() -> None:
    agent = ReqnRollStepDefinitionAgent(
        Settings(openai_api_key="", codex_executable="unavailable-test-codex")
    )
    request = StepDefinitionRequest(
        suite=_suite(
            gherkin=(
                "Scenario: Quote\n  Given a client\n  When it sends a quote\n"
                "  Then a quote is returned"
            )
        ),
        validation=_validation(False),
    )

    with pytest.raises(ValueError, match="Quality Gate-approved"):
        await agent.generate(request)


@pytest.mark.asyncio
async def test_step_definitions_require_automation_gherkin() -> None:
    agent = ReqnRollStepDefinitionAgent(
        Settings(openai_api_key="", codex_executable="unavailable-test-codex")
    )
    request = StepDefinitionRequest(suite=_suite(mode="manual"), validation=_validation(True))

    with pytest.raises(ValueError, match="no automation Gherkin"):
        await agent.generate(request)


@pytest.mark.asyncio
async def test_provider_failure_never_returns_incomplete_bindings(
    monkeypatch,
) -> None:
    async def unavailable(*args, **kwargs):
        raise CopilotGenerationError("GitHub Copilot usage quota is exhausted.")

    monkeypatch.setattr(CopilotAgentRunner, "generate_structured", unavailable)
    agent = ReqnRollStepDefinitionAgent(
        Settings(openai_api_key="", codex_executable="unavailable-test-codex")
    )
    request = StepDefinitionRequest(
        suite=_suite(
            gherkin=(
                "Scenario Outline: Quote\n"
                "  Given a <customerType> client\n"
                "  When it sends a quote\n"
                "  Then a quote is returned"
            )
        ),
        validation=_validation(True),
    )

    with pytest.raises(CopilotGenerationError, match="No incomplete files were returned"):
        await agent.generate(request)


def test_fallback_reuses_binding_for_steps_that_only_differ_by_quoted_value() -> None:
    first = _suite(
        gherkin=(
            'Scenario: Retail quote\n  Given a "retail" customer\n'
            "  When a quote is requested\n  Then a quote is returned"
        )
    ).test_cases[0]
    second = first.model_copy(
        update={
            "id": "TC-002",
            "title": "Business quote",
            "gherkin": (
                'Scenario: Business quote\n  Given a "business" customer\n'
                "  When a quote is requested\n  Then a quote is returned"
            ),
        }
    )

    artifact = ReqnRollStepDefinitionAgent._fallback_artifact("Quote API", [first, second])

    content = artifact.files[0].content
    assert content.count("[Given(") == 0
    assert "NotImplementedException" not in content
    given_coverage = [item for item in artifact.coverage if item.gherkin_step.startswith("Given")]
    assert [item.status for item in given_coverage] == ["blocked", "blocked"]
    assert given_coverage[0].binding == given_coverage[1].binding


@pytest.mark.asyncio
async def test_ai_output_reuses_local_support_files(monkeypatch, tmp_path) -> None:
    from app.agents.reqnroll_step_definition_agent import StepDefinitionArtifact
    from app.agents.reqnroll_validation import implementation_findings

    async def generate(*args, **kwargs):
        assert "OMIT unchanged helper files" in kwargs["prompt"]
        return StepDefinitionArtifact(
            files=[
                {
                    "path": "StepDefinitions/ExampleStepDefinition.cs",
                    "content": """using Reqnroll;
namespace Generated.StepDefinitions;
[Binding]
public class Steps {
    private readonly ApiScenario api;
    public Steps(ApiScenario api) { this.api = api; }
    [Then("the HTTP status should be 200")]
    public void Status() { api.AssertStatus(200); }
}""",
                }
            ],
            coverage=[
                {
                    "gherkin_step": "Then the HTTP status should be 200",
                    "status": "generated",
                    "binding": "Status",
                }
            ],
        )

    monkeypatch.setattr(CopilotAgentRunner, "generate_structured", generate)
    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    agent = ReqnRollStepDefinitionAgent(settings)
    result = await agent.generate(
        StepDefinitionRequest(
            suite=_suite(gherkin="Scenario: Status\n Then the HTTP status should be 200"),
            validation=_validation(True),
        )
    )
    assert {
        "StepDefinitions/ExampleStepDefinition.cs",
        "TestContext/testcontext.cs",
        "Utilities/ApprovedFixturesUtility.cs",
        "Services/ApiService.cs",
        "Models/ApiResponseModel.cs",
        "Builders/ApiClientbuilder.cs",
        "Input/TestData.Json",
        "Automation.csproj",
    } <= {file.path for file in result.files}
    assert implementation_findings(result, {"Then the HTTP status should be 200"}) == []

    async def unavailable(*args, **kwargs):
        raise AssertionError("Validated AI output should be reused without calling the provider")

    monkeypatch.setattr(CopilotAgentRunner, "generate_structured", unavailable)
    reused = await ReqnRollStepDefinitionAgent(settings).generate(
        StepDefinitionRequest(
            suite=_suite(gherkin="Scenario: Status\n Then the HTTP status should be 200"),
            validation=_validation(True),
        )
    )
    assert reused.files == result.files
    assert all(item.status == "reused" for item in reused.coverage)


@pytest.mark.asyncio
async def test_csharp_memory_reuses_duplicate_scenarios_after_restart(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from app.agents.artifact_runner import ArtifactGenerationRunner

    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    request = StepDefinitionRequest(
        suite=_suite(gherkin="Scenario: Status\n Then the response status is 200"),
        validation=_validation(True),
    )
    original = await ReqnRollStepDefinitionAgent(settings).generate(request)
    duplicate = request.suite.test_cases[0].model_copy(update={"id": "TC-NEW"})
    request.suite.test_cases.append(duplicate)
    provider = AsyncMock(side_effect=AssertionError("Duplicate scenarios must not call AI"))
    monkeypatch.setattr(ArtifactGenerationRunner, "generate_structured", provider)
    result = await ReqnRollStepDefinitionAgent(settings).generate(request)
    assert [f for f in result.files if f.path.endswith(".cs")] == [
        f for f in original.files if f.path.endswith(".cs")
    ]
    assert all(item.status == "reused" for item in result.coverage)
    assert "organizational memory" in result.notes[-1]
    provider.assert_not_awaited()
    request.validation.passed = False
    with pytest.raises(ValueError, match="Quality Gate"):
        await ReqnRollStepDefinitionAgent(settings).generate(request)


@pytest.mark.asyncio
async def test_partial_duplicate_csharp_is_supplied_as_knowledge(tmp_path, monkeypatch):
    from app.agents.artifact_runner import ArtifactGenerationRunner

    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    first = _suite(gherkin="Scenario: Status\n Then the response status is 200")
    agent = ReqnRollStepDefinitionAgent(settings)
    await agent.generate(StepDefinitionRequest(suite=first, validation=_validation(True)))
    changed = first.model_copy(deep=True)
    changed.test_cases.append(
        first.test_cases[0].model_copy(
            update={
                "id": "TC-002",
                "gherkin": "Scenario: Domain\n Then a quote is returned",
            }
        )
    )

    async def generate(*args, **kwargs):
        assert "VALIDATED C# KNOWLEDGE FOR OVERLAPPING SCENARIOS" in kwargs["prompt"]
        assert "AssertStatus(expectedStatus)" in kwargs["prompt"]
        raise CopilotGenerationError("offline")

    monkeypatch.setattr(ArtifactGenerationRunner, "generate_structured", generate)
    with pytest.raises(CopilotGenerationError, match="offline"):
        await agent.generate(StepDefinitionRequest(suite=changed, validation=_validation(True)))
    import sqlite3

    with sqlite3.connect(settings.organizational_memory_path) as connection:
        assert connection.execute("SELECT count(*) FROM reqnroll_memory").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_corrupt_csharp_memory_is_not_returned(tmp_path):
    import sqlite3

    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    request = StepDefinitionRequest(
        suite=_suite(gherkin="Scenario: Status\n Then the response status is 200"),
        validation=_validation(True),
    )
    agent = ReqnRollStepDefinitionAgent(settings)
    original = await agent.generate(request)
    for content in [
        '{"files": []}',
        original.model_dump_json().replace("api.AssertStatus(expectedStatus);", ""),
    ]:
        with sqlite3.connect(settings.organizational_memory_path) as connection:
            connection.execute("UPDATE reqnroll_memory SET artifact_json = ?", (content,))
        regenerated = await agent.generate(request)
        assert regenerated.files == original.files
        assert all(item.status == "generated" for item in regenerated.coverage)


def test_csharp_memory_identity_preserves_behavior_and_project_context():
    from app.agents.reqnroll_memory import ReqnRollMemory

    suite = _suite(gherkin='Scenario: Status\n Given fixture "Retail"')
    identity = ReqnRollMemory.identity(suite, "project-a", "policy")
    for field, value in [
        ("gherkin", 'Scenario: Status\n Given fixture "retail"'),
        ("preconditions", ["Requires authorization"]),
        ("test_data", [{"name": "customer", "value": "business", "purpose": "fixture"}]),
        ("steps", [{"action": "Send request", "expected_result": "Request rejected"}]),
    ]:
        changed = suite.model_copy(deep=True)
        changed.test_cases[0] = changed.test_cases[0].model_validate(
            {**changed.test_cases[0].model_dump(), field: value}
        )
        assert ReqnRollMemory.identity(changed, "project-a", "policy") != identity
    assert ReqnRollMemory.identity(suite, "project-b", "policy") != identity
    assert ReqnRollMemory.identity(suite, "project-a", "new policy") != identity
    changed = suite.model_copy(update={"assumptions": ["New contract"]})
    assert ReqnRollMemory.identity(changed, "project-a", "policy") != identity


@pytest.mark.asyncio
async def test_disabled_csharp_memory_does_not_write(tmp_path):
    settings = Settings(
        _env_file=None,
        organizational_memory_enabled=False,
        organizational_memory_path=tmp_path / "memory.db",
    )
    request = StepDefinitionRequest(
        suite=_suite(gherkin="Scenario: Status\n Then the response status is 200"),
        validation=_validation(True),
    )
    for _ in range(2):
        result = await ReqnRollStepDefinitionAgent(settings).generate(request)
        assert all(item.status == "generated" for item in result.coverage)
    assert not settings.organizational_memory_path.exists()


def test_bindings_only_never_generates_or_reads_full_pack(tmp_path, monkeypatch):
    from unittest.mock import Mock

    settings = Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    agent = ReqnRollStepDefinitionAgent(settings)
    agent.memory.candidates = Mock(side_effect=AssertionError("Must not read full-pack memory"))
    monkeypatch.setattr(
        agent, "generate", Mock(side_effect=AssertionError("Must not generate pack"))
    )
    source = _suite(
        gherkin=(
            'Scenario Outline: Quote\n Given a "retail" client\n And status <class>\n'
            " When it sends 2 requests\n Then a quote is returned\n"
            "Examples:\n | class |\n | valid |"
        )
    )
    source.test_cases.append(
        source.test_cases[0].model_copy(
            update={
                "id": "TC-2",
                "gherkin": 'Scenario: Other\n Given a "business" client',
            }
        )
    )
    artifact = agent.generate_bindings(
        StepDefinitionRequest(suite=source, validation=_validation(True))
    )
    assert len(artifact.files) == 1
    content = artifact.files[0].content
    assert content.count("[Given(") == 2
    assert "string arg1" in content
    assert "int arg1" in content
    assert content.count("PendingStepException") == 4
    assert "ApiScenario" not in content
    assert len(artifact.coverage) == 5
    assert artifact.coverage[0].binding == artifact.coverage[-1].binding
    assert all(item.status == "blocked" for item in artifact.coverage)
    assert not settings.organizational_memory_path.exists()


@pytest.mark.parametrize("manual,passed", [(True, True), (False, False)])
def test_bindings_only_requires_approved_automation(manual, passed):
    agent = ReqnRollStepDefinitionAgent(Settings(_env_file=None))
    request = StepDefinitionRequest(
        suite=_suite(
            mode="manual" if manual else "automation", gherkin="Scenario: Status\n Then OK"
        ),
        validation=_validation(passed),
    )
    with pytest.raises(ValueError):
        agent.generate_bindings(request)


@pytest.mark.asyncio
async def test_codegen_receives_current_report_and_preserves_historical_notes(
    monkeypatch, tmp_path
):
    import json

    from app.agents.reqnroll_step_definition_agent import StepDefinitionArtifact

    suite = _suite(gherkin="Scenario: Status\n Then the HTTP status should be 200")
    suite.coverage_notes = ["Earlier draft: Quality Gate failed."]
    suite.test_cases[0].acceptance_criteria_covered = ["FR-001", "BR-001"]
    report = _validation(True)

    async def generate(*args, **kwargs):
        prompt = kwargs["prompt"]
        evidence = prompt.split("APPLICATION QUALITY GATE REPORT\n", 1)[1].split("\n\n", 1)[0]
        assert json.loads(evidence) == report.model_dump(mode="json")
        assert "Earlier draft: Quality Gate failed." in prompt
        assert '"FR-001"' in prompt and '"BR-001"' in prompt
        assert "not rejected test design" in kwargs["instructions"]
        return StepDefinitionArtifact(
            files=[
                {
                    "path": "StepDefinitions/StatusStepDefinition.cs",
                    "content": """using Reqnroll;
namespace Generated.StepDefinitions;
[Binding] public class StatusSteps {
    private readonly ApiScenario api;
    public StatusSteps(ApiScenario api) { this.api = api; }
    [Then("the HTTP status should be 200")]
    public void Status() { api.AssertStatus(200); }
}""",
                }
            ],
            coverage=[
                {
                    "gherkin_step": "Then the HTTP status should be 200",
                    "status": "generated",
                    "binding": "Status",
                }
            ],
        )

    monkeypatch.setattr(CopilotAgentRunner, "generate_structured", generate)
    agent = ReqnRollStepDefinitionAgent(
        Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    )
    artifact = await agent.generate(StepDefinitionRequest(suite=suite, validation=report))
    assert artifact.coverage[0].status == "generated"
    assert suite.coverage_notes == ["Earlier draft: Quality Gate failed."]


@pytest.mark.asyncio
async def test_inconsistent_approval_is_rejected_before_provider_or_cache(monkeypatch, tmp_path):
    from unittest.mock import AsyncMock

    from app.agents.test_case_validator import ValidationFinding

    generate = AsyncMock()
    monkeypatch.setattr(CopilotAgentRunner, "generate_structured", generate)
    report = _validation(True)
    report.findings = [
        ValidationFinding(
            dimension="coverage",
            severity="error",
            message="Missing required case",
            test_case_ids=["TC-001"],
        )
    ]
    agent = ReqnRollStepDefinitionAgent(
        Settings(_env_file=None, organizational_memory_path=tmp_path / "memory.db")
    )
    with pytest.raises(ValueError, match="inconsistent"):
        await agent.generate(
            StepDefinitionRequest(
                suite=_suite(gherkin="Scenario: Status\n Then the response status is 200"),
                validation=report,
            )
        )
    generate.assert_not_awaited()
