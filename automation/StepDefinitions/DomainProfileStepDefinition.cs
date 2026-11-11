using Reqnroll;
using QualityLifecycle.Automation.TestContext;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class DomainProfileStepDefinition(DomainProfileScenarioContext context)
{
    [When("I create a custom domain profile")]
    public Task Create() => context.Service.Create();

    [When("I apply the custom domain profile")]
    public Task Activate() => context.Service.Activate();

    [When("I submit the {string} invalid domain profile")]
    public Task Invalid(string variant) => context.Service.Invalid(variant);

    [When("I update the domain profile with a stale revision")]
    public Task StaleUpdate() => context.Service.StaleUpdate();

    [When("I apply a domain selection with a stale revision")]
    public Task StaleSelection() => context.Service.StaleSelection();

    [When("I create a domain profile without authentication")]
    public Task Anonymous() => context.Service.AnonymousCreate();

    [Then("the domain profile response status is {int}")]
    public void AssertStatus(int expected) => context.Service.AssertStatus(expected);

    [Then("the original domain profile remains selected")]
    public Task AssertOriginal() => context.Service.AssertOriginal();

    [Then("new requests use the custom profile with finance context disabled")]
    public Task AssertActive() => context.Service.AssertActive();

    [AfterScenario]
    public async Task Cleanup()
    {
        await context.Service.Cleanup();
        context.Service.Dispose();
    }
}
