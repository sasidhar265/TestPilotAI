using NUnit.Framework;

namespace QualityLifecycle.Automation.Utilities;

public static class ConfidentialDataUtility
{
    public static void AssertNoProviderSecrets(string response)
    {
        var secrets = new[] { "OPENAI_API_KEY", "GEMINI_API_KEY", "COPILOT_GITHUB_TOKEN", "API_AUTH_TOKEN", "API_SESSION_COOKIE", "APP_PASSWORD" }
            .Select(name => new { Name = name, Value = ConfigurationUtility.GetValue(name) })
            .Where(secret => !string.IsNullOrWhiteSpace(secret.Value));
        foreach (var secret in secrets)
            Assert.That(response, Does.Not.Contain(secret.Value!), secret.Name);
    }
}
