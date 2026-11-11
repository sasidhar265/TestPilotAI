using Reqnroll;
using QualityLifecycle.Automation.TestContext;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class KnowledgeAgentStepDefinition(KnowledgeAgentScenarioContext context)
{
    [When("I create knowledge contributor {string}")]
    public Task Create(string fixture) => context.Service.Create(fixture);

    [When("I create a knowledge contributor without authentication")]
    public Task UnauthenticatedCreate() => context.Service.UnauthenticatedCreate();

    [When("I create a knowledge contributor with an unapproved model field")]
    public Task CreateWithModelOverride() => context.Service.CreateWithModelOverride();

    [When("I update knowledge contributor from {string} expecting revision {int}")]
    public Task Update(string fixture, int revision) => context.Service.Update(fixture, revision);

    [When("I review knowledge revision {int}")]
    public Task Review(int revision) => context.Service.Review(revision);

    [When("I review knowledge revision {int} without source approval")]
    public Task ReviewWithoutApproval(int revision) => context.Service.ReviewWithoutApproval(revision);

    [When("I {string} knowledge revision {int}")]
    public Task Action(string action, int revision) => context.Service.Action(action, revision);

    [Then("the knowledge response status is {int}")]
    public void AssertStatus(int expected) => context.Service.AssertStatus(expected);

    [Then("the active knowledge revision is {int}")]
    public Task AssertActive(int expected) => context.Service.AssertActive(expected);

    [Then("the knowledge contributor is included in the live agent catalog")]
    public Task AssertIncluded() => context.Service.AssertCatalog(true);

    [Then("the knowledge contributor is excluded from the live agent catalog")]
    public Task AssertExcluded() => context.Service.AssertCatalog(false);

    [When("I validate the exported knowledge contributor for import")]
    public Task ValidateExportImport() => context.Service.ValidateExportImport();

    [When("I validate a knowledge import with an unapproved model field")]
    public Task ValidateModelImport() => context.Service.ValidateImportWithModelOverride();

    [When("I validate an unsupported knowledge import format")]
    public Task ValidateUnsupportedImport() => context.Service.ValidateUnsupportedImport();

    [Then("the import result is a new draft definition without publication identity")]
    public void AssertImportDraft() => context.Service.AssertImportDraft();

    [AfterScenario]
    public async Task Cleanup()
    {
        await context.Service.Cleanup();
        context.Service.Dispose();
    }
}
