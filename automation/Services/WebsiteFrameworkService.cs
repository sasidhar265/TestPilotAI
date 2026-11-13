using System.IO.Compression;
using System.Text.Json;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;
namespace QualityLifecycle.Automation.Services;
public sealed class WebsiteFrameworkService(ApiService api)
{
    public async Task Build(string fixture)
    {
        using var request = WebsiteFrameworkRequestBuilder.Build(fixture);
        await api.RequestAsync(request);
    }
    private static JsonElement Unwrap(JsonElement root)
    {
        if (root.GetProperty("workflow").GetString() == "prompt-result")
            return root.GetProperty("result");
        return root;
    }
    public void AssertPack()
    {
        using var data = JsonDocument.Parse(api.ResponseBody);
        var root = data.RootElement;
        root = Unwrap(root);
        Assert.That(root.GetProperty("workflow").GetString(), Is.EqualTo("website-framework"));
        Assert.That(root.GetProperty("execution_status").GetString(), Is.EqualTo("not_run"));
        Assert.That(root.GetProperty("scenario_counts").GetProperty("smoke").GetInt32(), Is.Positive);
        using var bytes = new MemoryStream(Convert.FromBase64String(root.GetProperty("archive_base64").GetString()!));
        using var zip = new ZipArchive(bytes);
        var entries = zip.Entries.Select(item => item.FullName).ToList();
        Assert.That(entries, Does.Contain("Features/Smoke/Smoke.feature"));
        Assert.That(entries, Does.Contain("Pages/HomePage.cs"));
        Assert.That(entries, Does.Contain("Pages/BasePage.cs"));
        Assert.That(entries, Does.Contain("Pages/Components/NavigationComponent.cs"));
        Assert.That(entries, Does.Contain("Features/Sanity/Sanity.feature"));
        Assert.That(entries, Does.Contain("Features/Regression/Regression.feature"));
        Assert.That(entries, Does.Contain("Reqnroll/TestCategories.cs"));
        Assert.That(root.GetProperty("page_objects").GetArrayLength(), Is.Positive);
        Assert.That(root.GetProperty("test_suites").GetArrayLength(), Is.EqualTo(3));
        Assert.That(root.GetProperty("language").GetString(), Is.EqualTo("csharp"));
        Assert.That(root.GetProperty("framework").GetString(), Is.EqualTo("ReqnRoll"));
        Assert.That(root.GetProperty("automation_tool").GetString(), Is.EqualTo("Selenium"));
        Assert.That(root.GetProperty("target_framework").GetString(), Is.EqualTo("net10.0"));
        Assert.That(root.GetProperty("files").EnumerateArray().Any(file =>
            file.GetProperty("path").GetString() == "Pages/HomePage.cs"
            && file.GetProperty("content").GetString()!.Contains("class HomePage")), Is.True);
        Assert.That(entries, Does.Contain("StepDefinitions/WebsiteStepDefinition.cs"));
        Assert.That(entries, Does.Contain("Input/CaseData.Json"));
        using var manifest = new StreamReader(zip.GetEntry("Automation.csproj")!.Open());
        var project = manifest.ReadToEnd();
        Assert.That(project, Does.Contain("Selenium.WebDriver"));
        Assert.That(project, Does.Contain("DotNetSeleniumExtras.PageObjects.Core"));
        using var home = new StreamReader(zip.GetEntry("Pages/HomePage.cs")!.Open());
        Assert.That(home.ReadToEnd(), Does.Contain("[FindsBy"));
        using var factory = new StreamReader(zip.GetEntry("Services/PageCatalogService.cs")!.Open());
        Assert.That(factory.ReadToEnd(), Does.Contain("PageFactory.InitElements(driver, page)"));
        Assert.That(root.GetProperty("design_pattern").GetString(), Is.EqualTo("Page Object Model + PageFactory"));
    }
}
