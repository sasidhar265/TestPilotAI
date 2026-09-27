using Reqnroll;
using QualityLifecycle.Automation.Services;
namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class GuestAccessStepDefinition(GuestAccessService service)
{
    [Given("I have entered the temporary guest preview")]
    public Task EnterGuest() => service.EnterAsync();

    [When("the guest requests protected {string} using {string}")]
    public Task RequestProtected(string name, string method) => service.RequestProtectedAsync(name, method);

    [When("the guest opens the static workspace preview")]
    public Task RequestPreview() => service.RequestPreviewAsync();

    [Then("the guest response status is {int}")]
    public void AssertStatus(int expected) => service.AssertStatus(expected);

    [AfterScenario]
    public void Cleanup() => service.Dispose();
}
