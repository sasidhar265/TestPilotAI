using System.Text.Json;
using Microsoft.Extensions.Configuration;
namespace QualityLifecycle.Automation.Utilities;

public static class ConfigurationUtility
{
    private static readonly Lazy<IConfiguration> LocalSecrets = new(LoadLocalSecrets);

    private static IConfiguration LoadLocalSecrets()
    {
        var builder = new ConfigurationBuilder();
        var enabled = Environment.GetEnvironmentVariable("USER_SECRETS_ENABLED");
        var environment = Environment.GetEnvironmentVariable("ENVIRONMENT") ?? "development";
        if ((string.Equals(enabled, "true", StringComparison.OrdinalIgnoreCase) || enabled == "1")
            && string.Equals(environment, "development", StringComparison.OrdinalIgnoreCase))
        {
            var identifier = Environment.GetEnvironmentVariable("USER_SECRETS_ID");
            if (string.IsNullOrEmpty(identifier))
                builder.AddUserSecrets(typeof(ConfigurationUtility).Assembly, optional: true);
            else
                builder.AddUserSecrets(identifier, reloadOnChange: false);
        }
        return builder.Build();
    }

    public static string? GetValue(string name) =>
        Environment.GetEnvironmentVariable(name) ?? LocalSecrets.Value[name];

    public static string BaseUrl => GetValue("QUALITY_LIFECYCLE_BASE_URL")
        ?? "http://127.0.0.1:8000";
    public static bool ApiAuthConfigured => AuthenticationUtility.IsConfigured;
    public static string UnauthenticatedDescription()
    {
        using var data = JsonDocument.Parse(File.ReadAllText(
            Path.Combine(AppContext.BaseDirectory, "Input", "TestData.Json")));
        return data.RootElement.GetProperty("unauthenticatedDescription").GetString()
            ?? throw new InvalidOperationException("Missing unauthenticatedDescription test data.");
    }
}
