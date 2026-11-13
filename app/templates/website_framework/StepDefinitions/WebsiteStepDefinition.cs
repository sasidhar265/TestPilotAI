using Reqnroll;
using Website.Automation.Services;
using Website.Automation.TestContext;

namespace Website.Automation.StepDefinitions;

[Binding]
public sealed class WebsiteStepDefinition(WebsiteContext context)
{
    [Given("the website scenario {string}")]
    public void GivenCase(string id) => new ScenarioService(context).Load(id);
    [When("I open its public page")]
    public void OpenPage() => new ScenarioService(context).Open();
    [When("I select its published appearance option")]
    public void SelectAppearance() => new ScenarioService(context).SelectAppearance();
    [When("I follow its published navigation link")]
    public void FollowLink() => new ScenarioService(context).FollowLink();
    [Then("its published page title is displayed")]
    [Then("its published heading is visible")]
    [Then("its published control is visible")]
    [Then("its published destination opens")]
    [Then("its published appearance option is selected")]
    [Then("its published dropdown options are available")]
    [Then("its document finishes loading")]
    public void Verify() => new EvidenceService(context).Verify();
}
