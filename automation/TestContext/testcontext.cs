using QualityLifecycle.Automation.Services;
using QualityLifecycle.Automation.Utilities;
using Microsoft.Extensions.DependencyInjection;
namespace QualityLifecycle.Automation.TestContext;

public sealed class AutomationContext : IDisposable
{
    private readonly ServiceProvider provider;
    public ApiService Api { get; }
    public BrowserService Browser { get; } = new();

    public AutomationContext()
    {
        var services = new ServiceCollection();
        services.AddHttpClient<ApiService>(http => {
            http.BaseAddress = new Uri(ConfigurationUtility.BaseUrl);
            http.Timeout = TimeSpan.FromSeconds(60);
        });
        provider = services.BuildServiceProvider();
        Api = provider.GetRequiredService<ApiService>();
    }

    public void Dispose() => provider.Dispose();
}
