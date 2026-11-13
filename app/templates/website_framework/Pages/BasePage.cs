using OpenQA.Selenium;
using OpenQA.Selenium.Support.UI;
using SeleniumExtras.PageObjects;
using Website.Automation.Models;
using Website.Automation.Pages.Components;
using Website.Automation.Utilities;

namespace Website.Automation.Pages;

public abstract class BasePage(IWebDriver driver, BrowserSettingsModel settings)
{
    protected IWebDriver Driver { get; } = driver;
    protected WaitUtility Wait { get; } = new(driver, settings.WaitTimeoutSeconds);
    public abstract string RelativePath { get; }
    protected abstract IReadOnlyDictionary<string, Func<IWebElement>> ControlElements { get; }
    [FindsBy(How = How.CssSelector, Using = "h1,h2,h3")]
    protected IList<IWebElement> Headings { get; set; } = null!;
    protected abstract IReadOnlyDictionary<string, Action> NavigationActions { get; }
    protected NavigationComponent Navigation { get; } = new(driver, settings);
    public string Title => Driver.Title;
    public string Url => Driver.Url;
    public bool IsReady => ((IJavaScriptExecutor)Driver).ExecuteScript("return document.readyState")?.ToString() == "complete";

    public void Open()
    {
        Driver.Navigate().GoToUrl(settings.Resolve(RelativePath));
        Wait.Until(() => IsReady, $"Page did not finish loading: {RelativePath}");
        NUnit.Framework.TestContext.WriteLine($"Opened {Driver.Url}; title: {Driver.Title}");
    }
    public bool HeadingVisible(string expected) => Headings
        .Any(element => element.Displayed && Normalize(element.Text) == Normalize(expected));
    public bool ControlVisible(string key) => IsVisible(ControlElements[key]);
    public void FollowLink(string observedDestination) => NavigationActions[observedDestination]();
    public void SelectOption(string key, string publishedText) =>
        new SelectElement(ReadyControl(key)).SelectByText(publishedText);
    public string SelectedOption(string key) =>
        new SelectElement(ReadyControl(key)).SelectedOption.Text;
    public IReadOnlyList<string> Options(string key) =>
        new SelectElement(ReadyControl(key)).Options.Select(item => item.Text).ToList();
    private IWebElement ReadyControl(string key)
    {
        var element = ControlElements[key]();
        Wait.Until(() => element.Displayed && element.Enabled, $"Control is not ready: {key}");
        return element;
    }
    protected bool IsVisible(Func<IWebElement> resolve)
    {
        try { return resolve().Displayed; }
        catch (NoSuchElementException) { return false; }
        catch (StaleElementReferenceException) { return false; }
    }
    private static string Normalize(string text) => string.Join(" ", text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
}
