using System.Text.RegularExpressions;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;

namespace QualityLifecycle.Automation.Services;

public sealed class WorkspacePresentationService(ApiService api)
{
    private bool noStore;
    public async Task Inspect(string fixture)
    {
        var page = WorkspacePresentationRequestBuilder.Page(fixture);
        noStore = page.NoStore;
        using var request = page.Request;
        await api.RequestAsync(request);
    }
    public void AssertPresentation()
    {
        Assert.That((int)api.Response!.StatusCode, Is.EqualTo(200));
        Assert.That(api.ResponseBody, Does.Contain("/static/styles/workspace-ui.css?v="));
        Assert.That(api.ResponseBody, Does.Contain("/static/scripts/workspace-chrome.js?v="));
        Assert.That(Regex.Matches(api.ResponseBody, @"<h1(?:\s|>)").Count, Is.EqualTo(1));
        if (noStore)
            Assert.That(api.Response.Headers.CacheControl?.NoStore, Is.True);
    }
}
