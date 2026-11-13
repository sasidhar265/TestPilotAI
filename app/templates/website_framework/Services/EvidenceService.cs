using NUnit.Framework;
using System.Text.Json;
using Website.Automation.TestContext;
using Website.Automation.Utilities;

namespace Website.Automation.Services;

// Assertions stay outside page objects. Each case uses one independently named contract.
public sealed class EvidenceService(WebsiteContext context)
{
    public void Verify()
    {
        var checks = new Dictionary<string, Func<bool>>
        {
            ["title"] = () => context.Page.Title == context.Case.Expected,
            ["document"] = () => context.Page.IsReady,
            ["heading"] = () => context.Page.HeadingVisible(context.Case.Expected),
            ["control"] = () => context.Page.ControlVisible(context.Case.SelectorKey),
            ["selection"] = () => context.Page.SelectedOption(context.Case.SelectorKey) == context.Case.Expected,
            ["options"] = () => context.Page.Options(context.Case.SelectorKey).SequenceEqual(
                JsonSerializer.Deserialize<string[]>(context.Case.Expected)!),
            ["navigation"] = () =>
                new Uri(context.Page.Url).GetLeftPart(UriPartial.Path) == context.Settings.Resolve(context.Case.DestinationUrl).GetLeftPart(UriPartial.Path)
                && context.Page.Title == context.Case.DestinationTitle
        };
        var reason = $"{context.Case.Id}: {context.Case.Title}; expected {context.Case.Expected}; actual title {context.Page.Title}; URL {context.Page.Url}";
        new WaitUtility(context.Driver, context.Settings.WaitTimeoutSeconds).Until(checks[context.Case.Kind], reason);
        Assert.That(checks[context.Case.Kind](), Is.True, reason);
    }
}
