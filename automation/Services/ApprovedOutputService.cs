using System.Text.Json;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;

namespace QualityLifecycle.Automation.Services;

public sealed class ApprovedOutputService(ApiService api)
{
    private string artifactId = string.Empty;

    public async Task Approve()
    {
        using var request = ApprovedOutputRequestBuilder.Approve();
        await api.RequestAsync(request);
        using var response = JsonDocument.Parse(api.ResponseBody);
        artifactId = response.RootElement.GetProperty("artifacts")[0].GetProperty("sha256").GetString()![..12];
    }

    public async Task AssertVisible()
    {
        foreach (var path in new[] { "/api/workspace/knowledge", "/api/stlc" })
        {
            using var request = ApprovedOutputRequestBuilder.Read(path);
            await api.RequestAsync(request);
            Assert.That((int)api.Response!.StatusCode, Is.EqualTo(200));
            Assert.That(api.ResponseBody, Does.Contain(artifactId));
        }
    }

    public async Task AssertSelectedCases()
    {
        using var request = ApprovedOutputRequestBuilder.Read("/api/workspace/knowledge/outputs/" + artifactId);
        await api.RequestAsync(request);
        Assert.That((int)api.Response!.StatusCode, Is.EqualTo(200));
        using var result = JsonDocument.Parse(api.ResponseBody);
        var cases = result.RootElement.GetProperty("output").GetProperty("suite")
            .GetProperty("test_cases").EnumerateArray().Select(c => c.GetProperty("id").GetString());
        var expected = ApprovedOutputRequestBuilder.Input().GetProperty("selected_case_ids")
            .EnumerateArray().Select(id => id.GetString());
        Assert.That(cases, Is.EquivalentTo(expected));
    }
}
