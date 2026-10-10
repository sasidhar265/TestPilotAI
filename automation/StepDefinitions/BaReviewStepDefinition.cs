using Reqnroll;
using QualityLifecycle.Automation.Services;
namespace QualityLifecycle.Automation.StepDefinitions;
[Binding]
public sealed class BaReviewStepDefinition
{
    private readonly BaReviewService service = new();
    [When("I submit the BA review fixture {string}")]
    public Task Review(string name) => service.Review(name);
    [Then("the BA agent rejects the invalid BRD without a review outcome")]
    public void Rejected() => service.AssertRejected();
    [AfterScenario]
    public void Cleanup() => service.Dispose();
}
