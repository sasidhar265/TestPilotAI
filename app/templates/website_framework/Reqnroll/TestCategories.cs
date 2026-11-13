// NUnit fixture metadata makes categories discoverable without Gherkin tags.
namespace Website.Automation.Features.Smoke
{
    [NUnit.Framework.Category("Smoke")]
    public partial class SmokeWebsiteReadinessFeature { }
}
namespace Website.Automation.Features.Sanity
{
    [NUnit.Framework.Category("Sanity")]
    public partial class SanityWebsiteNavigationFeature { }
}
namespace Website.Automation.Features.Regression
{
    [NUnit.Framework.Category("Regression")]
    public partial class RegressionWebsiteContractsFeature { }
}
