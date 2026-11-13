using Reqnroll;
using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.TestContext;
namespace QualityLifecycle.Automation.StepDefinitions;
[Binding]
public sealed class WebsiteFrameworkStepDefinition(AutomationContext context)
{
    private readonly WebsiteFrameworkService service = new(context.Api);
    [When("I build the {string} website framework")]
    public Task Build(string fixture) => service.Build(fixture);
    [Then("the website framework is a downloadable Selenium CSharp BDD page object pack")]
    public void AssertPack() => service.AssertPack();
}
