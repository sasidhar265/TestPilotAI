using Reqnroll;
using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.TestContext;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class WorkflowStepDefinition(AutomationContext context)
{
    private readonly WorkflowService service = new(context.Api);

    [When("I validate the {string} workflow handoff")]
    public Task ValidateHandoff(string fixture) => service.ValidateHandoff(fixture);

    [Then("the workflow response contains {string}")]
    public void AssertResponse(string text) => service.AssertResponse(text);
}
