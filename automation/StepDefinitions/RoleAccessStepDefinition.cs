using Reqnroll;
using Microsoft.Extensions.DependencyInjection;
using QualityLifecycle.Automation.Utilities;
using QualityLifecycle.Automation.Services;
namespace QualityLifecycle.Automation.StepDefinitions;
[Binding]
public sealed class RoleAccessStepDefinition
{
    private readonly ServiceProvider provider = RoleAccessFixtureUtility.ClientProvider();
    private readonly RoleAccessService service;
    public RoleAccessStepDefinition() => service = new(provider.GetRequiredService<IHttpClientFactory>());
    [Given("an isolated account using role fixture {string}")]
    public Task CreateAccount(string fixture) => service.CreateAccount(fixture);
    [When("I exercise its permitted and restricted operations")]
    public Task Exercise() => service.Exercise();
    [Then("its profile and operation responses match the role fixture")]
    public void AssertRole() => service.AssertCapabilities();
    [When("an administrator changes its assigned role")]
    public Task ChangeRole() => service.ChangeRole();
    [Then("its existing browser session is rejected")]
    public void AssertRevoked() => service.AssertRevoked();
    [AfterScenario("role-access")]
    public async Task Dispose() { try { await service.Cleanup(); } finally { service.Dispose(); provider.Dispose(); } }
}
