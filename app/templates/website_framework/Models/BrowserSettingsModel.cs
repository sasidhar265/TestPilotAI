using System.Text.Json;

namespace Website.Automation.Models;

public sealed class BrowserSettingsModel
{
    public string BaseUrl { get; set; } = string.Empty;
    public string Browser { get; set; } = "chrome";
    public bool Headless { get; set; } = true;
    public int WaitTimeoutSeconds { get; set; } = 15;
    public int PageLoadTimeoutSeconds { get; set; } = 45;
    public int CommandTimeoutSeconds { get; set; } = 60;
    public int WindowWidth { get; set; } = 1440;
    public int WindowHeight { get; set; } = 1000;

    public static BrowserSettingsModel Load()
    {
        var settings = JsonSerializer.Deserialize<BrowserSettingsModel>(File.ReadAllText(
            Path.Combine(AppContext.BaseDirectory, "Input", "TestData.Json")),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
            ?? throw new InvalidOperationException("Input/TestData.Json is required.");
        settings.BaseUrl = Environment.GetEnvironmentVariable("WEBSITE_BASE_URL") ?? settings.BaseUrl;
        settings.Browser = Environment.GetEnvironmentVariable("BROWSER") ?? settings.Browser;
        settings.Headless = bool.Parse(Environment.GetEnvironmentVariable("HEADLESS") ?? settings.Headless.ToString());
        var origin = new Uri(settings.BaseUrl, UriKind.Absolute);
        if (origin.Scheme is not ("http" or "https")) throw new InvalidOperationException("WEBSITE_BASE_URL must be HTTP(S).");
        if (settings.WaitTimeoutSeconds <= 0 || settings.PageLoadTimeoutSeconds <= 0 || settings.CommandTimeoutSeconds <= 0)
            throw new InvalidOperationException("Browser timeouts must be positive.");
        return settings;
    }
    public Uri Resolve(string observedPathOrUrl)
    {
        var path = Uri.TryCreate(observedPathOrUrl, UriKind.Absolute, out var absolute)
            ? absolute.PathAndQuery : observedPathOrUrl;
        return new Uri(new Uri(BaseUrl), path);
    }
}
