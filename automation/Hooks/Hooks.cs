using Reqnroll;
using QualityLifecycle.Automation.TestContext;
namespace QualityLifecycle.Automation.Hooks;

[Binding]
public sealed class Hooks(AutomationContext context)
{
    [AfterScenario]
    public async Task Cleanup()
    {
        try
        {
            await context.Browser.DisposeAsync();
        }
        finally { context.Api.Dispose(); }
    }
}
