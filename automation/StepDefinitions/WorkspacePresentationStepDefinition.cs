using Reqnroll;
using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.TestContext;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class WorkspacePresentationStepDefinition(AutomationContext context)
{
    private readonly WorkspacePresentationService service = new(context.Api);
    [When("I inspect the {string} workspace page presentation")]
    public Task Inspect(string fixture) => service.Inspect(fixture);
    [Then("the workspace page has shared styles and navigation with one main heading")]
    public void Presentation() => service.AssertPresentation();
}
