using Reqnroll;
using QualityLifecycle.Automation.Services;
namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class AutoFinanceStepDefinition
{
    private readonly FinanceService service = new();
    [When("I request the auto finance domain catalogue")]
    public Task Catalogue() => service.Catalogue();
    [When("I validate the auto finance fixture {string}")]
    public Task Calculate(string name) => service.Calculate(name);
    [Then("the auto finance catalogue identifies reference content and valid mappings")]
    public void AssertCatalogue() => service.AssertCatalogue();
    [Then("the auto finance result matches its fixture expectations")]
    public void AssertFixture() => service.AssertFixture();
    [AfterScenario]
    public void Cleanup() => service.Dispose();
}
