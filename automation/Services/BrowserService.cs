using Microsoft.Playwright;
using NUnit.Framework;
using QualityLifecycle.Automation.Utilities;
namespace QualityLifecycle.Automation.Services;

public sealed class BrowserService : IAsyncDisposable
{
    private IPlaywright? playwright;
    private IBrowser? browser;
    public IPage? Page
    {
        get; private set;
    }
    private string BaseUrl => ConfigurationUtility.BaseUrl;
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
            var username = ConfigurationUtility.GetValue("APP_USERNAME");
            var password = ConfigurationUtility.GetValue("APP_PASSWORD");
            Assert.That(username, Is.Not.Null.And.Not.Empty,
                "Set APP_USERNAME when browser login is enabled.");
            Assert.That(password, Is.Not.Null.And.Not.Empty,
                "Set APP_PASSWORD when browser login is enabled.");
            await page.Locator("#username").FillAsync(username!);
            await page.Locator("#password").FillAsync(password!);
            await page.RunAndWaitForResponseAsync(
                async () => await page.Locator("#login-button").ClickAsync(),
                response => response.Url.Contains("/api/auth/login", StringComparison.Ordinal)
                    && response.Ok
            );
            await page.WaitForURLAsync(
                url => !url.EndsWith("/login", StringComparison.OrdinalIgnoreCase),
                new PageWaitForURLOptions { WaitUntil = WaitUntilState.Commit }
            );
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (browser is not null)
            await browser.DisposeAsync();
        playwright?.Dispose();
    }
}
