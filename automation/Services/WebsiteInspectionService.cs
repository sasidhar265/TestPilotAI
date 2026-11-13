using System.Text.Json;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;

namespace QualityLifecycle.Automation.Services;

public sealed class WebsiteInspectionService(ApiService api)
{
    public async Task Inspect(string fixture)
    {
        using var request = WebsiteInspectionRequestBuilder.Build(fixture);
        await api.RequestAsync(request);
    }

    public void AssertEvidence(string content)
    {
        using var result = JsonDocument.Parse(api.ResponseBody);
        Assert.That(result.RootElement.GetProperty("description").GetString(), Does.Contain(content));
        Assert.That(result.RootElement.GetProperty("pages").GetArrayLength(), Is.EqualTo(1));
    }

    public void AssertSource()
    {
        using var result = JsonDocument.Parse(api.ResponseBody);
        Assert.That(result.RootElement.GetProperty("website_source_receipt").GetString(), Is.Not.Empty);
        Assert.That(result.RootElement.GetProperty("warnings").GetArrayLength(), Is.GreaterThan(0));
        Assert.That(result.RootElement.GetProperty("description").GetString(), Does.Contain("untrusted"));
    }
}
