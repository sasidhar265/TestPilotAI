using System.Text.Json;
using System.Net;
using Microsoft.Extensions.DependencyInjection;
using QualityLifecycle.Automation.Models;
namespace QualityLifecycle.Automation.Utilities;
public static class RoleAccessFixtureUtility
{
    public static RoleAccessFixtureModel Read(string name)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "RoleAccess.Json")));
        return document.RootElement.GetProperty(name).Deserialize<RoleAccessFixtureModel>(
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidOperationException("Missing role fixture.");
    }
    public static RoleAccountModel Account() => JsonSerializer.Deserialize<RoleAccountModel>(
        File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Input", "RoleAccount.Json")),
        new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
        ?? throw new InvalidOperationException("Missing role account data.");
    public static ServiceProvider ClientProvider()
    {
        var services = new ServiceCollection();
        foreach (var name in new[] { "role-admin", "role-user" })
            services.AddHttpClient(name, client =>
            {
                client.BaseAddress = new Uri(ConfigurationUtility.BaseUrl);
                client.Timeout = TimeSpan.FromSeconds(30);
            }).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
            {
                CookieContainer = new CookieContainer(), AllowAutoRedirect = false
            });
        return services.BuildServiceProvider();
    }
    public static string AdminUser => ConfigurationUtility.GetValue("ROLE_TEST_ADMIN_USER")
        ?? throw new InvalidOperationException("Configure ROLE_TEST_ADMIN_USER for isolated role checks.");
    public static string AdminPassword => ConfigurationUtility.GetValue("ROLE_TEST_ADMIN_PASSWORD")
        ?? throw new InvalidOperationException("Configure ROLE_TEST_ADMIN_PASSWORD for isolated role checks.");
}
