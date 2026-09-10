using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Playwright;
using NUnit.Framework;

namespace QualityLifecycle.Automation.Support;

public sealed class AutomationContext : IAsyncDisposable
{
    private readonly HttpClient http;
    private IPlaywright? playwright;
    private IBrowser? browser;

    public AutomationContext()
    {
        BaseUrl = Environment.GetEnvironmentVariable("QUALITY_LIFECYCLE_BASE_URL")
            ?? "http://127.0.0.1:8000";
        http = new HttpClient { BaseAddress = new Uri(BaseUrl, UriKind.Absolute) };
    }

    public string BaseUrl { get; }
    public HttpResponseMessage? Response { get; private set; }
    public string ResponseBody { get; private set; } = string.Empty;
    public IPage? Page { get; private set; }
    public bool ApiAuthConfigured => !string.IsNullOrWhiteSpace(
        Environment.GetEnvironmentVariable("API_AUTH_TOKEN"));

    public async Task RequestAsync(HttpRequestMessage request)
    {
        Response?.Dispose();
        Response = await http.SendAsync(request);
        ResponseBody = await Response.Content.ReadAsStringAsync();
    }

    public async Task OpenBrowserAsync()
    {
        playwright = await Playwright.CreateAsync();
        browser = await playwright.Chromium.LaunchAsync(new BrowserTypeLaunchOptions
        {
            Headless = true,
        });
        var page = await browser.NewPageAsync();
        Page = page;
        await page.GotoAsync(BaseUrl, new PageGotoOptions { WaitUntil = WaitUntilState.DOMContentLoaded });
        if (page.Url.EndsWith("/login", StringComparison.OrdinalIgnoreCase))
        {
            var username = Environment.GetEnvironmentVariable("APP_USERNAME");
            var password = Environment.GetEnvironmentVariable("APP_PASSWORD");
            Assert.That(username, Is.Not.Null.And.Not.Empty,
                "Set APP_USERNAME when browser login is enabled.");
            Assert.That(password, Is.Not.Null.And.Not.Empty,
                "Set APP_PASSWORD when browser login is enabled.");
            await page.Locator("#username").FillAsync(username!);
            await page.Locator("#password").FillAsync(password!);
            await page.Locator("#login-button").ClickAsync();
            await page.WaitForURLAsync(url => !url.EndsWith("/login", StringComparison.OrdinalIgnoreCase));
        }
    }

    public async ValueTask DisposeAsync()
    {
        Response?.Dispose();
        http.Dispose();
        if (browser is not null) await browser.DisposeAsync();
        playwright?.Dispose();
    }
}
