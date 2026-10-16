using Reqnroll;
using QualityLifecycle.Automation.Services;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class LifecycleGovernanceStepDefinition : IDisposable
{
    private readonly LifecycleGovernanceService service = new();
    [Given("a signed-in lifecycle administrator has a requirements project")]
    public Task Create() => service.Create();
    [When("the human completes the lifecycle through {string}")]
    public Task Complete(string target) => service.CompleteThrough(target);
    [When("the human advances without lifecycle evidence")]
    public Task Missing() => service.AdvanceWithoutEvidence();
    [When("the human submits an outdated lifecycle revision")]
    public Task Stale() => service.Stale();
    [When("the human requests lifecycle rework")]
    public Task Reject() => service.Reject();
    [When("the human changes the lifecycle requirements baseline")]
    public Task ChangeSource() => service.ChangeSource();
    [When("an invited developer attempts the current lifecycle transition")]
    public Task Developer() => service.DeveloperAttempts();
    [Then("the lifecycle operation returns {int}")]
    public void Status(int status) => service.AssertStatus(status);
    [Then("the lifecycle is {string} after reloading")]
    public Task Stage(string stage) => service.AssertStage(stage);
    [Then("four version-specific human lifecycle approvals are retained")]
    public void Approvals() => service.AssertApprovals();
    [Then("earlier lifecycle evidence is flagged as impacted")]
    public void Impact() => service.AssertImpact();
    [When("the human links requirements stories and tests then revises the requirement")]
    public Task LinkedRecords() => service.LinkedRecordsAndImpact();
    [Then("existing testing agents coexist with lifecycle agents and enforced provider models")]
    public Task CatalogueAndModels() => service.AssertCatalogueAndHealth();
    [Then("the lifecycle dashboard queue matches the project state")]
    public Task Queue() => service.AssertQueue();
    [Then("story readiness is denied before refinement and allowed after human handoffs")]
    public Task StoryReadiness() => service.AssertStoryReadinessGate();
    [Then("the ordered SDLC workspace follows human gates and returns to the rework step")]
    public Task Sequence() => service.AssertSequence();
    [Then("inline requirement edits and comments persist through stakeholder approval")]
    public Task InlineApproval() => service.InlineApproval();
    [Then("stale inline review comments are rejected without losing version history")]
    public Task InlineStale() => service.InlineStale();
    [Then("developer inline review access preserves requirement editing permissions")]
    public Task InlineDeveloper() => service.InlineDeveloper();
    [Then("an unknown inline AI suggestion is rejected without modifying the requirement")]
    public Task InlineUnknownSuggestion() => service.InlineUnknownSuggestion();
    [AfterScenario]
    public Task Cleanup() => service.Cleanup();
    public void Dispose() => service.Dispose();
}
