using OpenQA.Selenium;
using OpenQA.Selenium.Chrome;
using OpenQA.Selenium.Edge;
using OpenQA.Selenium.Firefox;
using Website.Automation.Models;

namespace Website.Automation.Services;

public static class DriverFactoryService
{
    public static IWebDriver Create(BrowserSettingsModel settings)
    {
        var factories = new Dictionary<string, Func<IWebDriver>>(StringComparer.OrdinalIgnoreCase)
        {
            ["chrome"] = () => Chrome(settings),
            ["firefox"] = () => Firefox(settings),
            ["edge"] = () => Edge(settings)
        };
        if (!factories.TryGetValue(settings.Browser, out var create))
            throw new InvalidOperationException("BROWSER must be chrome, firefox or edge.");
        var driver = create();
        driver.Manage().Timeouts().PageLoad = TimeSpan.FromSeconds(settings.PageLoadTimeoutSeconds);
        driver.Manage().Window.Size = new System.Drawing.Size(settings.WindowWidth, settings.WindowHeight);
        return driver;
    }
    private static IWebDriver Chrome(BrowserSettingsModel settings)
    {
        var options = new ChromeOptions();
        if (settings.Headless) options.AddArgument("--headless=new");
        var binary = Environment.GetEnvironmentVariable("CHROME_BINARY");
        if (!string.IsNullOrWhiteSpace(binary)) options.BinaryLocation = binary;
        var directory = Environment.GetEnvironmentVariable("CHROMEDRIVER_DIRECTORY");
        var service = string.IsNullOrWhiteSpace(directory)
            ? ChromeDriverService.CreateDefaultService() : ChromeDriverService.CreateDefaultService(directory);
        return new ChromeDriver(service, options, TimeSpan.FromSeconds(settings.CommandTimeoutSeconds));
    }
    private static IWebDriver Firefox(BrowserSettingsModel settings)
    {
        var options = new FirefoxOptions();
        if (settings.Headless) options.AddArgument("-headless");
        return new FirefoxDriver(options);
    }
    private static IWebDriver Edge(BrowserSettingsModel settings)
    {
        var options = new EdgeOptions();
        if (settings.Headless) options.AddArgument("--headless=new");
        return new EdgeDriver(options);
    }
}
