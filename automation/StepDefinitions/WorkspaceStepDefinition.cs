using System.Net;
using System.Text.Json;
using NUnit.Framework;
using Reqnroll;
using QualityLifecycle.Automation.TestContext;
using QualityLifecycle.Automation.Builders;
using QualityLifecycle.Automation.Utilities;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class WorkspaceStepDefinition
{
    private readonly AutomationContext context;

    public WorkspaceStepDefinition(AutomationContext context) => this.context = context;

    [Given("the Quality Lifecycle Studio is available")]
    public async Task VerifyAvailability()
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "/api/health");
        await context.Api.RequestAsync(request);
        Assert.That(context.Api.Response!.StatusCode, Is.EqualTo(HttpStatusCode.OK));
    }

    [When("I request the health endpoint")]
    public async Task RequestHealth()
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "/api/health");
        await context.Api.RequestAsync(request);
    }

    [When("I submit a generation request with description {string}")]
    public Task SubmitGeneration(string description) => SendGeneration(description, authenticated: true);

    private async Task SendGeneration(string description, bool authenticated)
    {
        using var request = GenerationRequestBuilder.Build(description, authenticated);
        await context.Api.RequestAsync(request);
    }

    [When("I submit a generation request without credentials")]
    public Task SubmitUnauthenticatedGeneration() =>
        SendGeneration(ConfigurationUtility.UnauthenticatedDescription(), authenticated: false);

    [When("I open the workspace in a browser")]
    public Task OpenWorkspace() => context.Browser.OpenBrowserAsync();

    [Then("the response status is {int}")]
    public void AssertResponseStatus(int status) =>
        Assert.That((int)context.Api.Response!.StatusCode, Is.EqualTo(status), context.Api.ResponseBody);

    [Then("the health response identifies the FastAPI runtime")]
    public void AssertRuntime()
    {
        using var json = JsonDocument.Parse(context.Api.ResponseBody);
        Assert.That(json.RootElement.GetProperty("execution_host").GetString(),
            Is.EqualTo("local-fastapi-uvicorn"));
    }

    [Then("the response must not contain a provider secret")]
    public void AssertNoProviderSecret() =>
        ConfidentialDataUtility.AssertNoProviderSecrets(context.Api.ResponseBody);

    [Given("API bearer authentication is configured")]
    [Given("API authentication is configured")]
    public void RequireApiAuth() =>
        Assert.That(ConfigurationUtility.ApiAuthConfigured, Is.True,
            "Configure API_AUTH_TOKEN or an authenticated API_SESSION_COOKIE for the security feature.");

    [Then("the page title contains {string}")]
    public async Task AssertTitle(string value) =>
        Assert.That(await context.Browser.Page!.TitleAsync(), Does.Contain(value));

    [Then("the generation form is visible")]
    public async Task AssertGenerationForm() =>
        Assert.That(await context.Browser.Page!.Locator("#generate-form").IsVisibleAsync(), Is.True);

    [Then("the generation submit button is disabled until requirements are supplied")]
    public async Task AssertSubmitDisabled() =>
        Assert.That(await context.Browser.Page!.Locator("#generate").IsDisabledAsync(), Is.True);

    [Then("the generation target includes {string}")]
    public async Task AssertGenerationTarget(string value) =>
        Assert.That(await context.Browser.Page!.Locator("#output-target").TextContentAsync(), Does.Contain(value));

    [Then("the model selector is visible")]
    public async Task AssertModelSelector() =>
        Assert.That(await context.Browser.Page!.Locator("#llm-model").IsVisibleAsync(), Is.True);
}
