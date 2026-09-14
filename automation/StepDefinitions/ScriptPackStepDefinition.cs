using Reqnroll;
using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.TestContext;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class ScriptPackStepDefinition(AutomationContext context)
{
    private readonly ScriptPackService service = new(context.Api);

    [When("I generate the {string} script pack")]
    public Task Generate(string fixture) => service.Send(fixture, "generate");

    [When("I download the {string} script pack")]
    public Task Download(string fixture) => service.Send(fixture, "download");

    [Then("the script pack includes {string} containing {string}")]
    public void AssertFile(string path, string content) => service.AssertFile(path, content);

    [Then("the script pack preserves its input case mappings")]
    public void AssertMappings() => service.AssertMappings();

    [Then("the script archive includes {string}")]
    public Task AssertArchive(string path) => service.AssertArchive(path);
}
