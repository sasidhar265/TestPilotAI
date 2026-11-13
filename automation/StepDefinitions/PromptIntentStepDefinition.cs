using Reqnroll;
using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.TestContext;
namespace QualityLifecycle.Automation.StepDefinitions;
[Binding]
public sealed class PromptIntentStepDefinition(AutomationContext context)
{
    private readonly PromptIntentService service = new(context.Api);
    [When("I interpret the {string} task prompt")]
    public Task Interpret(string fixture) => service.Interpret(fixture);
    [Then("the selected task workflow is {string}")]
    public void AssertWorkflow(string workflow) => service.AssertWorkflow(workflow);
    [Then("the task interpretation asks for clarification")]
    public void AssertQuestions() => service.AssertQuestions();
}
