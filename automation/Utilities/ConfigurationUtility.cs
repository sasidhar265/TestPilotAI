using System.Text.Json;
namespace QualityLifecycle.Automation.Utilities;

public static class ConfigurationUtility
{
    public static string BaseUrl => Environment.GetEnvironmentVariable("QUALITY_LIFECYCLE_BASE_URL")
        ?? "http://127.0.0.1:8000";
    public static bool ApiAuthConfigured => !string.IsNullOrWhiteSpace(
        Environment.GetEnvironmentVariable("API_AUTH_TOKEN"));
    public static string UnauthenticatedDescription()
    {
        using var data = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(AppContext.BaseDirectory, "Input", "TestData.Json")));
        return data.RootElement.GetProperty("unauthenticatedDescription").GetString()
            ?? throw new InvalidOperationException("Missing unauthenticatedDescription test data.");
    }
}
