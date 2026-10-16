using Reqnroll;
using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.TestContext;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class SdlcStepDefinition(AutomationContext context)
{
    private readonly SdlcService service = new(context.Api);

    [Given("a new SDLC delivery project exists")]
    public Task CreateProject() => service.CreateProject();

    [When("I request the SDLC agent catalogue")]
    public Task Catalog() => service.Catalog();

    [When("I save the {string} SDLC Requirements fixture")]
    public Task SavePlan(string fixture) => service.SavePlan(fixture);

    [When("I manually write a downstream SDLC output")]
    public Task WriteDownstream() => service.WriteDownstream();

    [When("I approve the first SDLC Requirements version")]
    public Task ApprovePlan() => service.ApprovePlan();

    [When("I request the SDLC project history")]
    public Task History() => service.ProjectHistory();

    [When("I submit the {string} SDLC mission")]
    public Task Mission(string fixture) => service.SubmitMission(fixture);

    [When("I request an unknown SDLC delivery run")]
    public Task UnknownRun() => service.UnknownRun();

    [When("I {string} an unknown SDLC delivery run")]
    public Task UnknownRunOperation(string operation) => service.UnknownRunOperation(operation);

    [Then("all seven SDLC stage agents and mandatory models are discoverable")]
    public void Agents() => service.AssertAgentCatalog();

    [Then("SDLC history preserves both versions and approval belongs only to version one")]
    public void Versions() => service.AssertVersionHistory();
}
