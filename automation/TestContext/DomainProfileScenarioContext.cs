using QualityLifecycle.Automation.Services;

namespace QualityLifecycle.Automation.TestContext;

public sealed class DomainProfileScenarioContext
{
    public DomainProfileService Service { get; } = new();
}
