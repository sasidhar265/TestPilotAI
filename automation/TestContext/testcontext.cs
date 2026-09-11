using QualityLifecycle.Automation.Services;
namespace QualityLifecycle.Automation.TestContext;

public sealed class AutomationContext
{
    public ApiService Api { get; } = new();
    public BrowserService Browser { get; } = new();
}
