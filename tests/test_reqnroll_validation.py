import pytest

from app.agents.reqnroll_implementations import support_files
from app.agents.reqnroll_step_definition_agent import (
    ReqnRollStepDefinitionAgent,
    StepCoverage,
    StepDefinitionArtifact,
    StepDefinitionFile,
    StepDefinitionRequest,
)
from app.agents.reqnroll_validation import implementation_findings
from app.agents.runner import CopilotAgentRunner
from app.agents.test_case_validator import ValidationReport
from app.config import Settings
from app.models import TestCase as Case
from app.models import TestStep as Step
from app.models import TestSuite as Suite


def artifact(body='api.LoadFixture("approved");'):
    return StepDefinitionArtifact(
        files=[
            StepDefinitionFile(
                path="StepDefinitions/ExampleStepDefinition.cs",
                content="""
using Reqnroll;
[Binding]
public class Steps
{
    private readonly ApiScenario api;
    public Steps(ApiScenario api) { this.api = api; }
    [Given(@"^the approved request is prepared$")]
    public void Prepare() { BODY }
}
""".replace("BODY", body),
            ),
            *[StepDefinitionFile(path=path, content=source) for path, source in support_files([])],
        ],
        coverage=[
            StepCoverage(
                gherkin_step="Given the approved request is prepared",
                status="generated",
                binding="Prepare",
            )
        ],
    )


@pytest.mark.parametrize(
    "source",
    [
        "using RestSharp;",
        "class Transport { RestClient client; }",
        "class Transport { System.Net.WebClient client; }",
        "class Transport { System.Net.HttpWebRequest request; }",
        "using Flurl.Http;",
        "class Transport { Microsoft.Playwright.IAPIRequestContext client; }",
    ],
)
def test_csharp_api_transport_rejects_alternative_clients(source):
    result = artifact()
    result.files.append(StepDefinitionFile(path="Services/TransportService.cs", content=source))
    assert any("System.Net.Http.HttpClient" in item for item in implementation_findings(result))


def test_csharp_httpclient_templates_allow_alternative_names_in_comments_and_strings():
    result = artifact()
    result.files.append(
        StepDefinitionFile(
            path="Services/TransportService.cs",
            content='// RestSharp is forbidden\nclass Note { const string Text = "WebRequest"; }',
        )
    )
    assert not implementation_findings(result)


def request(step="the approved request is prepared"):
    return StepDefinitionRequest(
        suite=Suite(
            feature_name="API",
            output_format="bdd",
            test_cases=[
                Case(
                    id="TC-1",
                    title="Request",
                    objective="Prepare request",
                    category="smoke",
                    priority="P1",
                    execution_mode="automation",
                    feasibility_reason="API fixture",
                    steps=[Step(action="Prepare request", expected_result="Request configured")],
                    gherkin=f"Scenario: Request\n Given {step}",
                )
            ],
        ),
        validation=ValidationReport(
            passed=True, score=100, acceptance_criteria_total=0, acceptance_criteria_covered=0
        ),
    )


@pytest.mark.parametrize(
    "body",
    [
        "throw new NotImplementedException();",
        'throw new System.NotImplementedException("implement");',
        "ScenarioContext.StepIsPending(); // TODO",
        "context.Pending();",
        "throw new PendingStepException();",
        "",
        "// implement this later",
        "/* implement this later */",
        'throw new InvalidOperationException("implementation unavailable");',
        "return;",
        "return Task.CompletedTask;",
        "return Task.FromResult(true);",
        "Assert.Pass();",
        "Assert.True(true);",
    ],
)
def test_placeholder_and_fake_success_methods_are_rejected(body) -> None:
    assert implementation_findings(artifact(body), {"Given the approved request is prepared"})


def test_guards_belong_in_services_not_step_definitions() -> None:
    body = """if (api == null) throw new InvalidOperationException("No context");
api.LoadFixture("https://fixture.example/a");"""
    assert any(
        "step definitions must delegate" in finding
        for finding in implementation_findings(
            artifact(body), {"Given the approved request is prepared"}
        )
    )
    value = artifact()
    value.files.append(
        StepDefinitionFile(
            path="Services/PreparationService.cs",
            content="public class PreparationService { public void Prepare(ApiScenario api) { "
            + body
            + " } }",
        )
    )
    assert not implementation_findings(value, {"Given the approved request is prepared"})


def test_placeholder_in_supporting_helper_is_rejected() -> None:
    value = artifact()
    value.files.append(
        StepDefinitionFile(
            path="Helper.cs",
            content="""
public class ApiScenario {
    public void LoadFixture(string fixture) { throw new NotImplementedException(); }
}""",
        )
    )
    assert implementation_findings(value)


def test_missing_method_wrong_kind_and_missing_coverage_are_rejected() -> None:
    value = artifact()
    value.coverage[0].binding = "DoesNotExist"
    assert any("No Given binding" in finding for finding in implementation_findings(value))
    value.coverage[0].binding = "Prepare"
    value.files[0].content = value.files[0].content.replace("[Given(", "[When(")
    assert any("No Given binding" in finding for finding in implementation_findings(value))
    value.coverage = []
    assert any(
        "Missing step coverage" in finding
        for finding in implementation_findings(value, {"Given the approved request is prepared"})
    )


@pytest.mark.asyncio
async def test_complete_common_bindings_do_not_need_ai(monkeypatch) -> None:
    async def unexpected(*args, **kwargs):
        pytest.fail("Complete common bindings should not require a provider call")

    monkeypatch.setattr(CopilotAgentRunner, "generate_structured", unexpected)
    value = await ReqnRollStepDefinitionAgent(
        Settings(
            _env_file=None,
            codex_executable="unavailable-test-codex",
            organizational_memory_enabled=False,
        )
    ).generate(request('a request built from "approved"'))
    assert not implementation_findings(value)


@pytest.mark.asyncio
async def test_incomplete_ai_output_is_revised_before_returning(monkeypatch) -> None:
    calls = []

    async def generate(*args, **kwargs):
        calls.append(kwargs["prompt"])
        return artifact("throw new NotImplementedException();") if len(calls) == 1 else artifact()

    monkeypatch.setattr(CopilotAgentRunner, "generate_structured", generate)
    value = await ReqnRollStepDefinitionAgent(
        Settings(
            _env_file=None,
            codex_executable="unavailable-test-codex",
            organizational_memory_enabled=False,
        )
    ).generate(request())
    assert len(calls) == 2
    assert "IMPLEMENTATION REVIEW" in calls[1]
    assert not implementation_findings(value)


@pytest.mark.asyncio
async def test_persistently_incomplete_ai_output_returns_no_files(monkeypatch) -> None:
    calls = []

    async def generate(*args, **kwargs):
        calls.append(kwargs["prompt"])
        return artifact("throw new NotImplementedException();")

    monkeypatch.setattr(CopilotAgentRunner, "generate_structured", generate)
    with pytest.raises(ValueError, match="No files were returned"):
        await ReqnRollStepDefinitionAgent(
            Settings(
                _env_file=None,
                codex_executable="unavailable-test-codex",
                organizational_memory_enabled=False,
            )
        ).generate(request())
    assert len(calls) == 2
