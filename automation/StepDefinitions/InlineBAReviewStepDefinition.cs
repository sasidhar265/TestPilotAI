using Reqnroll;
using QualityLifecycle.Automation.Services;

namespace QualityLifecycle.Automation.StepDefinitions;

[Binding]
public sealed class InlineBAReviewStepDefinition(InlineBAReviewService review)
{
    [Given("a signed-in BA reviewer has the synthetic BRD {string}")]
    public Task Create(string name) => review.Create(name);
    [When("the reviewer analyses the saved BRD baseline")]
    public Task Analyse() => review.Analyse();
    [Then("the BA review contains a source-linked {string} finding")]
    public void Finding(string type) => review.Finding(type);
    [Then("AI analysis has not signed off or changed the original BRD")]
    public Task Unchanged() => review.NoAutomaticApproval();
    [When("the BA rejects the recommendation and reanalyses unchanged material")]
    public Task Reanalyse() => review.RejectAndReanalyse();
    [Then("the rejected proposal and human audit history survive reloading")]
    public Task Rejection() => review.AssertRejection();
    [Then("pending findings block BA signoff")]
    public Task Pending() => review.PendingBlocks();
    [When("the BA rejects the recommendation and signs off the reviewed baseline")]
    public Task Signoff() => review.RejectAndSignoff();
    [Then("the human BA signoff is recorded without business approval")]
    public Task Human() => review.AssertHumanSignoff();
    [Then("a new BRD version invalidates the previous BA review")]
    public Task Revised() => review.RevisedBaseline();
    [Then("resolving the calculation finding does not permit BA signoff")]
    public Task Blocked() => review.CalculationBlocks();
    [Then("an invited developer cannot decide BA findings")]
    public Task Developer() => review.DeveloperDenied();
    [Then("a different account cannot read the BA review")]
    public Task Outsider() => review.OutsiderDenied();
    [When("the BA records the finding action {string}")]
    public Task Action(string action) => review.Action(action);
    [Then("the saved finding review status is {string}")]
    public Task Status(string status) => review.AssertAction(status);
    [When("the reviewer cancels a queued BRD analysis")]
    public Task Cancel() => review.Cancel();
    [Then("the BA analysis stays cancelled after reloading")]
    public Task Cancelled() => review.AssertCancelled();
    [Then("the AI creates source-linked draft supporting requirements with an attributed history")]
    public Task SupportingDrafts() => review.AssertSupportingDrafts();
    [When("the BA edits a supporting draft and reanalyses the BRD")]
    public Task EditDraft() => review.EditAndReanalyseDraft();
    [Then("reanalysis preserves the human draft without creating duplicate supporting records")]
    public Task PreserveDraft() => review.AssertHumanDraftPreserved();
    [When("the BA analyses a new version of the same BRD")]
    public Task NewVersion() => review.AnalyseNewBaseline();
    [Then("the earlier supporting drafts remain impacted and the new version has separate drafts")]
    public Task BaselineDrafts() => review.AssertBaselineDrafts();
    [Then("no supporting requirement drafts were created")]
    public Task NoDrafts() => review.AssertNoSupportingDrafts();
    [Given("a BA project member is ready to draft stories")]
    public Task AddBA() => review.AddBA();
    [Then("the BA cannot create a story without current baseline signoff")]
    public Task StoryBlocked() => review.StoryDraftBlocked();
    [Then("the BA can create linked draft stories without granting business approval")]
    public Task StoryCreated() => review.StoryDraftCreated();
    [When("the BRD is revised after BA signoff")]
    public Task ReviseSignedBRD() => review.ReviseAfterSignoff();
    [Then("the BA can download source backed business documents and metrics")]
    public Task Documents() => review.DownloadBusinessDocuments();
    [Then("an unrelated account cannot download the business documents")]
    public Task DocumentIsolation() => review.OutsiderDocumentDenied();
    [Then("pending suggestions prevent creating an updated BRD")]
    public Task PendingRevision() => review.PendingRevisionBlocked();
    [When("the BA creates the updated BRD and requests revalidation")]
    public Task RevisedDocument() => review.CreateRevisedBRD();
    [Then("the updated BRD reflects the {string} decision and preserves the original")]
    public Task RevisedContent(string action) => review.AssertRevisedBRD(action);
    [Then("the updated BRD has fresh assessments without automatic approval")]
    public Task RevisedAssessment() => review.AssertRevalidatedBRD();
    [Then("the previous review cannot overwrite the updated BRD")]
    public Task StaleRevision() => review.StaleRevisionBlocked();
    [Then("open feedback requests block signoff of the updated BRD")]
    public Task OpenFeedback() => review.OpenFeedbackBlocksRevisionSignoff();
}
