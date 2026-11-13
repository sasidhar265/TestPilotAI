using OpenQA.Selenium;
using Reqnroll;
using Website.Automation.Models;
using Website.Automation.Services;
using Website.Automation.TestContext;

namespace Website.Automation.Hooks;

[Binding]
public sealed class Hooks(WebsiteContext context, ScenarioContext scenario)
{
    [BeforeScenario]
    public void Start()
    {
        context.Settings = BrowserSettingsModel.Load();
        context.Driver = DriverFactoryService.Create(context.Settings);
    }
    [AfterScenario(Order = 0)]
    public void CaptureFailure()
    {
        if (scenario.TestError is null || context.Driver is not ITakesScreenshot camera) return;
        try
        {
            var root = new DirectoryInfo(AppContext.BaseDirectory);
            while (root.Parent is not null && !File.Exists(Path.Combine(root.FullName, "Automation.csproj"))) root = root.Parent;
            var directory = Environment.GetEnvironmentVariable("TEST_RESULTS_DIRECTORY")
                ?? Path.Combine(root.FullName, "TestResults", "Reports");
            Directory.CreateDirectory(directory);
            var file = Path.Combine(directory, $"failure-{Guid.NewGuid():N}.png");
            camera.GetScreenshot().SaveAsFile(file);
            NUnit.Framework.TestContext.AddTestAttachment(file, scenario.ScenarioInfo.Title);
        }
        catch (Exception error)
        {
            NUnit.Framework.TestContext.WriteLine($"Screenshot could not be saved: {error.Message}");
        }
    }
    [AfterScenario(Order = 100)]
    public void Stop()
    {
        try { context.Driver?.Quit(); }
        finally { context.Driver?.Dispose(); }
    }
}
