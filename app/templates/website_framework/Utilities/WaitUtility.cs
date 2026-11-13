using OpenQA.Selenium;
using OpenQA.Selenium.Support.UI;

namespace Website.Automation.Utilities;

public sealed class WaitUtility(IWebDriver driver, int seconds)
{
    private WebDriverWait Create(string reason)
    {
        var wait = new WebDriverWait(driver, TimeSpan.FromSeconds(seconds)) { Message = reason };
        wait.IgnoreExceptionTypes(typeof(NoSuchElementException), typeof(StaleElementReferenceException));
        return wait;
    }
    public void Until(Func<bool> condition, string reason) => Create(reason).Until(_ => condition());
    public IWebElement Element(Func<IEnumerable<IWebElement>> elements, Func<IWebElement, bool> matches) =>
        Create("No visible, enabled published element matched.").Until(_ =>
            elements().FirstOrDefault(element => element.Displayed && element.Enabled && matches(element)))!;
    public IWebElement Element(By locator, Func<IWebElement, bool> matches) =>
        Create($"No visible, enabled element matched {locator}.").Until(browser =>
            browser.FindElements(locator).FirstOrDefault(element =>
                element.Displayed && element.Enabled && matches(element)))!;
}
