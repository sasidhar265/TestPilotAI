using Reqnroll;
using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.TestContext;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class ApprovedOutputStepDefinition(AutomationContext context)
{
    private readonly ApprovedOutputService service = new(context.Api);

    [When("I approve the stored health test fixture")]
    public Task Approve() => service.Approve();

    [Then("the approved artifact is visible in saved outputs and project records")]
    public Task AssertVisible() => service.AssertVisible();

    [Then("the saved artifact includes only the approved test cases")]
    public Task AssertSelectedCases() => service.AssertSelectedCases();
}
