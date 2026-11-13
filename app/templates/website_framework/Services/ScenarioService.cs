using Website.Automation.TestContext;
using Website.Automation.Utilities;

namespace Website.Automation.Services;

public sealed class ScenarioService(WebsiteContext context)
{
    public void Load(string id)
    {
        context.Case = CaseDataUtility.Load(id);
        context.Page = new PageCatalogService(context.Driver, context.Settings).Create(context.Case.PageId);
        NUnit.Framework.TestContext.WriteLine($"{context.Case.Id}: {context.Case.Title} [{context.Case.Category}]");
    }
    public void Open() => context.Page.Open();
    public void SelectAppearance()
    {
        context.Page.Open();
        context.Page.SelectOption(context.Case.SelectorKey, context.Case.Expected);
    }
    public void FollowLink()
    {
        context.Page.Open();
        context.Page.FollowLink(context.Case.DestinationUrl);
    }
}
