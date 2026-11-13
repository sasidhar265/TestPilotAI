using Reqnroll;
using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.TestContext;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class WebsiteInspectionStepDefinition(AutomationContext context)
{
    private readonly WebsiteInspectionService service = new(context.Api);

    [When("I inspect the {string} website source")]
    public Task Inspect(string fixture) => service.Inspect(fixture);

    [Then("the website evidence includes {string}")]
    public void AssertEvidence(string content) => service.AssertEvidence(content);

    [Then("the website evidence has a signed source and inspection limitations")]
    public void AssertSource() => service.AssertSource();
}
