using System.Net.Http;
using System.Text.Json;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;
using QualityLifecycle.Automation.Models;
using QualityLifecycle.Automation.Utilities;
namespace QualityLifecycle.Automation.Services;
public sealed class BaReviewService : IDisposable
{
    private readonly HttpClient client = new() { BaseAddress = new Uri(ConfigurationUtility.BaseUrl), Timeout = TimeSpan.FromSeconds(30) };
    private BaReviewFixtureModel? fixture;
    private HttpResponseMessage? response;
    private string body = "";
    public async Task Review(string name)
    {
        fixture = BaReviewFixtureUtility.Read(name);
        using var request = BaReviewRequestBuilder.Build(fixture);
        response?.Dispose();
        response = await client.SendAsync(request);
        body = await response.Content.ReadAsStringAsync();
    }
    public void AssertRejected()
    {
        Assert.That((int)response!.StatusCode, Is.EqualTo(fixture!.Status));
        using var data = JsonDocument.Parse(body);
        Assert.That(data.RootElement.TryGetProperty("detail", out _), Is.True);
        Assert.That(data.RootElement.TryGetProperty("outcome", out _), Is.False);
    }
    public void Dispose() { response?.Dispose(); client.Dispose(); }
}
