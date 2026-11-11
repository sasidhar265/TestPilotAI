using Reqnroll;
using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.TestContext;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class WorkspacePresentationStepDefinition(AutomationContext context)
{
    private readonly WorkspacePresentationService service = new(context.Api);

    [Then("the {string} page follows the current workspace presentation contract")]
    public Task AssertPage(string name) => service.AssertPage(name);

    [Then("the live agent catalog preserves the approved core workflow order")]
    public Task AssertCatalog() => service.AssertCatalog();
}
