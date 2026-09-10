using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using NUnit.Framework;
using Reqnroll;
using QualityLifecycle.Automation.Support;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class WorkspaceSteps
{
    private readonly AutomationContext context;

    public WorkspaceSteps(AutomationContext context) => this.context = context;

    [Given("the Quality Lifecycle Studio is available")]
    public async Task VerifyAvailability()
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "/api/health");
        await context.RequestAsync(request);
        Assert.That(context.Response!.StatusCode, Is.EqualTo(HttpStatusCode.OK));
    }

    [When("I request the health endpoint")]
    public async Task RequestHealth()
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, "/api/health");
        await context.RequestAsync(request);
    }

    [When("I submit a generation request with description {string}")]
    public async Task SubmitGeneration(string description)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "/api/generate")
        {
            Content = JsonContent.Create(new { description }),
        };
        await context.RequestAsync(request);
    }

    [When("I submit a generation request without credentials")]
    public Task SubmitUnauthenticatedGeneration() => SubmitGeneration("A valid requirement description");

    [When("I open the workspace in a browser")]
    public Task OpenWorkspace() => context.OpenBrowserAsync();

    [Then("the response status is {int}")]
    public void AssertResponseStatus(int status) =>
        Assert.That((int)context.Response!.StatusCode, Is.EqualTo(status), context.ResponseBody);

    [Then("the health response identifies the FastAPI runtime")]
    public void AssertRuntime()
    {
        using var json = JsonDocument.Parse(context.ResponseBody);
        Assert.That(json.RootElement.GetProperty("execution_host").GetString(),
            Is.EqualTo("local-fastapi-uvicorn"));
    }

    [Then("the response must not contain a provider secret")]
    public void AssertNoProviderSecret()
    {
        foreach (var variable in new[] { "OPENAI_API_KEY", "GEMINI_API_KEY", "COPILOT_GITHUB_TOKEN", "API_AUTH_TOKEN" })
        {
            var secret = Environment.GetEnvironmentVariable(variable);
            if (!string.IsNullOrWhiteSpace(secret))
                Assert.That(context.ResponseBody, Does.Not.Contain(secret), variable);
        }
    }

    [Given("API bearer authentication is configured")]
    public void RequireApiAuth() =>
        Assert.That(context.ApiAuthConfigured, Is.True,
            "Set API_AUTH_TOKEN when running the security feature.");

    [Then("the page title contains {string}")]
    public async Task AssertTitle(string value) =>
        Assert.That(await context.Page!.TitleAsync(), Does.Contain(value));

    [Then("the generation form is visible")]
    public async Task AssertGenerationForm() =>
        Assert.That(await context.Page!.Locator("#generation-form").IsVisibleAsync(), Is.True);

    [Then("the generation submit button is disabled until requirements are supplied")]
    public async Task AssertSubmitDisabled() =>
        Assert.That(await context.Page!.Locator("#generate").IsDisabledAsync(), Is.True);

    [Then("the generation target includes {string}")]
    public async Task AssertGenerationTarget(string value) =>
        Assert.That(await context.Page!.Locator("#generation-target").TextContentAsync(), Does.Contain(value));

    [Then("the model selector is visible")]
    public async Task AssertModelSelector() =>
        Assert.That(await context.Page!.Locator("#llm-model").IsVisibleAsync(), Is.True);
}
