import json
from pathlib import Path

import pytest
from test_automation_layout import request

from app.agents.reqnroll_implementations import common_step
from app.agents.reqnroll_step_definition_agent import ReqnRollStepDefinitionAgent
from app.automation_pack import shared_assets
from app.automation_style import step_style_findings
from app.quotation_contract import PAYLOAD_PATH, quotation_instructions


@pytest.mark.asyncio
async def test_provider_cannot_replace_the_approved_request_model(monkeypatch):
    from app.agents.artifact_runner import ArtifactGenerationRunner
    from app.agents.reqnroll_step_definition_agent import (
        StepDefinitionArtifact,
        StepDefinitionRequest,
    )
    from app.config import Settings
    from app.quotation_contract import quotation_sources

    async def generate(self, definition, **kwargs):
        sources = quotation_sources()
        altered = StepDefinitionArtifact(
            files=[
                {
                    "path": "Models/QuotationRequestModel.cs",
                    "content": sources["Models/QuotationRequestModel.cs"] + "\n// changed contract",
                }
            ]
        )
        return kwargs["validate"](altered)

    monkeypatch.setattr(ArtifactGenerationRunner, "generate_structured", generate)
    item = request()
    item.suite.test_cases[0].gherkin = "Scenario: Domain\n Given a domain quotation is prepared"
    agent = ReqnRollStepDefinitionAgent(
        Settings(_env_file=None, organizational_memory_enabled=False)
    )
    with pytest.raises(ValueError, match="unchanged"):
        await agent.generate(StepDefinitionRequest(suite=item.suite, validation=item.validation))


def test_exact_approved_request_is_exported_without_new_fields():
    payload = json.loads(shared_assets(request().suite)["Input/QuotationRequest.Json"])
    assert payload == {
        "Outlet": {"code": "OUTLET001"},
        "Finance": {"ProductId": "PROD123"},
        "Vehicle": {
            "CapCode": "CAP456",
            "VehicleRegistrationNumber": "REG789",
            "VehicleRegstrationDate": "2023-01-01",
            "VehicleMake": "Toyota",
            "PriceTotal": 25000.00,
            "YearOfManufacture": 2022,
            "ExteriorColor": "Red",
            "QualifyingOrMargin": "Qualifying",
        },
        "Parameters": {
            "Deposit": 5000.00,
            "Term": 36,
            "AnnualMileage": 12000,
            "CustomerRate": 5.5,
            "PartExchange": 0.0,
            "Settlement": 0.0,
            "CalcTargetType": "Deposit",
        },
    }
    assert (
        json.loads(
            (Path(__file__).parents[1] / "automation/Input/QuotationRequest.Json").read_text()
        )
        == payload
    )
    assert PAYLOAD_PATH.read_text() in quotation_instructions()


@pytest.mark.parametrize(
    "extension,source",
    [
        ("cs", "public void Step() { if (ready) service.Send(); }"),
        ("java", "void step() { switch (kind) { case 1: service.send(); } }"),
        ("js", 'Then("result", () => ready ? service.pass() : service.fail());'),
        ("ts", 'Then("result", () => { if (ready) service.send(); });'),
        ("rb", 'Then("result") do\n send_request unless ready\nend'),
        ("py", "def step(context):\n    context.result = 1 if context.ok else 0"),
        ("py", "def step(context):\n    match context.state:\n        case 1: context.send()"),
    ],
)
def test_conditional_step_definitions_are_rejected(extension, source):
    assert step_style_findings(f"StepDefinitions/QuotationStepDefinition.{extension}", source)


@pytest.mark.parametrize(
    "extension,source",
    [
        ("cs", 'public void Step() { service.Send("if switch ? :"); /* if */ }'),
        ("cs", 'public void Step() { service.Send(value?.Name ?? "default"); }'),
        ("py", 'def step(context):\n    # if\n    context.service.send("if else")'),
        ("js", 'Then("if the switch is enabled", () => service.send());'),
        ("rb", 'Then("if enabled") do\n service.send_request # if ready\nend'),
    ],
)
def test_thin_adapters_and_condition_words_in_strings_are_allowed(extension, source):
    assert not step_style_findings(f"StepDefinitions/QuotationStepDefinition.{extension}", source)


def test_quotation_binding_routes_through_typed_builder_context():
    suite = request().suite
    artifact = ReqnRollStepDefinitionAgent._fallback_artifact("Quotation API", suite.test_cases)
    assert "api.LoadQuotationFixture(fixture)" in artifact.files[0].content
    assert not step_style_findings(artifact.files[0].path, artifact.files[0].content)
    assert (
        common_step("Given", "the approved quotation request")[2] == "api.LoadQuotationRequest();"
    )
    assert any(file.path == "Builders/QuotationRequestbuilder.cs" for file in artifact.files)


def test_existing_repository_steps_follow_no_branching_policy():
    for source in (Path(__file__).parents[1] / "automation/StepDefinitions").glob("*.cs"):
        assert not step_style_findings("StepDefinitions/" + source.name, source.read_text())


def test_moving_a_binding_into_services_does_not_bypass_the_step_policy():
    assert step_style_findings(
        "Services/ExampleService.cs",
        """
        [Binding] public class Example {
            [Given("a request")] public void Prepare() { if (ready) api.Send(); }
        }
    """,
    )
