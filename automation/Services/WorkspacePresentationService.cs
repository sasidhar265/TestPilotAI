using System.Text.Json;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;

namespace QualityLifecycle.Automation.Services;

public sealed class WorkspacePresentationService(ApiService api)
{
    public async Task AssertPage(string name)
    {
        var fixture = WorkspacePresentationRequestBuilder.Page(name);
        using var request = KnowledgeAgentRequestBuilder.Build(HttpMethod.Get, fixture.Path);
        await api.RequestAsync(request);
        Assert.That((int)api.Response!.StatusCode, Is.EqualTo(200));
        foreach (var text in fixture.Contains)
            Assert.That(api.ResponseBody, Does.Contain(text));
        foreach (var text in fixture.Excludes)
            Assert.That(api.ResponseBody, Does.Not.Contain(text));
        Assert.That(api.Response.Headers.CacheControl!.NoStore, Is.True);
    }

    public async Task AssertCatalog()
    {
        using var request = KnowledgeAgentRequestBuilder.Build(HttpMethod.Get, "/api/agents");
        await api.RequestAsync(request);
        using var document = JsonDocument.Parse(api.ResponseBody);
        var expected = WorkspacePresentationRequestBuilder.CatalogIds();
        var actual = document.RootElement.EnumerateArray().Take(expected.Length)
            .Select(item => item.GetProperty("id").GetString()).ToArray();
        Assert.That(actual, Is.EqualTo(expected));
    }
}
