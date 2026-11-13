using OpenQA.Selenium;
using SeleniumExtras.PageObjects;
using Website.Automation.Models;
using Website.Automation.Utilities;

namespace Website.Automation.Pages.Components;

public sealed class NavigationComponent
{
    private readonly BrowserSettingsModel settings;
    private readonly WaitUtility wait;
    [FindsBy(How = How.CssSelector, Using = "a[href]")]
    private IList<IWebElement> PublishedLinks { get; set; } = null!;

    public NavigationComponent(IWebDriver driver, BrowserSettingsModel settings)
    {
        this.settings = settings;
        wait = new WaitUtility(driver, settings.WaitTimeoutSeconds);
        PageFactory.InitElements(driver, this);
    }
    public void FollowPublishedLink(string observedDestination)
    {
        var destination = settings.Resolve(observedDestination).AbsoluteUri;
        var link = wait.Element(() => PublishedLinks,
            element => element.GetDomProperty("href") == destination);
        link.Click();
    }
}
