using Reqnroll;
using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.TestContext;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class CodeGenerationStepDefinition(AutomationContext context)
{
    private readonly CodeGenerationService service = new(context.Api);

    [When("I request an automation pack with {string} design validation")]
    public Task RequestPack(string validation) => service.RequestPack(validation);

    [Then("code generation reports {string}")]
    public void AssertMessage(string message) => service.AssertMessage(message);

    [Then("the automation pack contains executable bindings and current input data")]
    public void AssertCompletePack() => service.AssertCompletePack();
}
