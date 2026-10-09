using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;
using QualityLifecycle.Automation.Models;
using QualityLifecycle.Automation.Utilities;
namespace QualityLifecycle.Automation.Services;

public sealed class FinanceService : IDisposable
{
    private readonly ServiceProvider provider;
    private readonly FinanceClient client;
    private FinanceFixtureModel? fixture;
    private HttpResponseMessage? response;
    private string body = "";

    public FinanceService()
    {
        var services = new ServiceCollection();
        services.AddHttpClient<FinanceClient>(http => {
            http.BaseAddress = new Uri(ConfigurationUtility.BaseUrl);
            http.Timeout = TimeSpan.FromSeconds(30);
        });
        provider = services.BuildServiceProvider();
        client = provider.GetRequiredService<FinanceClient>();
    }
    public async Task Catalogue()
    {
        using var request = FinanceRequestBuilder.Catalogue();
        await Send(request);
    }
    public async Task Calculate(string name)
    {
        fixture = FinanceFixtureUtility.Read(name);
        using var request = FinanceRequestBuilder.Calculation(fixture);
        await Send(request);
    }
    private async Task Send(HttpRequestMessage request)
    {
        response?.Dispose();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        response = await client.SendAsync(request, timeout.Token);
        body = await response.Content.ReadAsStringAsync(timeout.Token);
    }
    public void AssertCatalogue()
    {
        Assert.That((int)response!.StatusCode, Is.EqualTo(200));
        using var document = JsonDocument.Parse(body);
        var root = document.RootElement;
        Assert.That(root.GetProperty("reference_only").GetBoolean(), Is.True);
        Assert.That(root.GetProperty("products").GetArrayLength(), Is.GreaterThan(0));
        Assert.That(root.GetProperty("journeys").GetArrayLength(), Is.GreaterThan(0));
        Assert.That(root.GetProperty("version").GetString(), Is.Not.Empty);
        var products = root.GetProperty("products").EnumerateArray().Select(p => p.GetProperty("id").GetString()).ToHashSet();
        foreach (var mapping in root.GetProperty("mappings").EnumerateArray())
        {
            Assert.That(products, Does.Contain(mapping.GetProperty("product_id").GetString()));
            Assert.That(mapping.GetProperty("requirement_version").GetInt32(), Is.GreaterThan(0));
        }
    }
    public void AssertFixture()
    {
        Assert.That((int)response!.StatusCode, Is.EqualTo(fixture!.Status));
        using var document = JsonDocument.Parse(body);
        var root = document.RootElement;
        if (fixture.Status != 200)
        {
            Assert.That(root.TryGetProperty("detail", out _), Is.True);
            return;
        }
        foreach (var expected in fixture.Expected.EnumerateObject())
            Assert.That(root.GetProperty("result").GetProperty(expected.Name).GetString(), Is.EqualTo(expected.Value.GetString()));
        Assert.That(root.GetProperty("convention").GetString(), Is.Not.Empty);
        Assert.That(root.GetProperty("scope").GetString(), Does.Contain("Reference arithmetic only"));
        if (fixture.Matches.HasValue)
            Assert.That(root.GetProperty("matches_observed").GetBoolean(), Is.EqualTo(fixture.Matches.Value));
    }
    public void Dispose() { response?.Dispose(); provider.Dispose(); }
}
