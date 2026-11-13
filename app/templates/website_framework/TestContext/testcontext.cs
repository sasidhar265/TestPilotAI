using OpenQA.Selenium;
using Website.Automation.Models;
using Website.Automation.Pages;

namespace Website.Automation.TestContext;

public sealed class WebsiteContext
{
    public IWebDriver Driver { get; set; } = null!;
    public BrowserSettingsModel Settings { get; set; } = null!;
    public ObservedCaseModel Case { get; set; } = null!;
    public BasePage Page { get; set; } = null!;
}
