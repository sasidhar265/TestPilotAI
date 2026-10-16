using System.Text.Json;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;

namespace QualityLifecycle.Automation.Services;

public sealed class SdlcService(ApiService api)
{
    private string project = string.Empty;

    public async Task CreateProject()
    {
        using var request = SdlcRequestBuilder.Post("projects", "project");
        await api.RequestAsync(request);
        Assert.That((int)api.Response!.StatusCode, Is.EqualTo(201));
        using var response = JsonDocument.Parse(api.ResponseBody);
        project = response.RootElement.GetProperty("id").GetString()!;
    }

    public async Task Catalog()
    {
        using var request = SdlcRequestBuilder.Get("agents");
        await api.RequestAsync(request);
    }

    public async Task SavePlan(string fixture)
    {
        using var request = SdlcRequestBuilder.Post($"projects/{project}/artifacts/requirements-input", fixture);
        await api.RequestAsync(request);
    }

    public async Task WriteDownstream()
    {
        using var request = SdlcRequestBuilder.Post($"projects/{project}/artifacts/design", "downstream");
        await api.RequestAsync(request);
    }

    public async Task ApprovePlan()
    {
        using var request = SdlcRequestBuilder.Post($"projects/{project}/artifacts/requirements-input/reviews", "approval");
        await api.RequestAsync(request);
    }

    public async Task ProjectHistory()
    {
        using var request = SdlcRequestBuilder.Get($"projects/{project}");
        await api.RequestAsync(request);
    }

    public async Task SubmitMission(string fixture)
    {
        using var request = SdlcRequestBuilder.Post($"projects/{project}/runs", fixture);
        await api.RequestAsync(request);
    }

    public async Task UnknownRun()
    {
        using var request = SdlcRequestBuilder.Get("runs/00000000000000000000000000000000");
        await api.RequestAsync(request);
    }

    public async Task UnknownRunOperation(string operation)
    {
        using var request = SdlcRequestBuilder.Post("runs/00000000000000000000000000000000/" + operation, "empty");
        await api.RequestAsync(request);
    }

    public void AssertAgentCatalog()
    {
        using var response = JsonDocument.Parse(api.ResponseBody);
        var stages = response.RootElement.GetProperty("agents").EnumerateArray()
            .Select(agent => agent.GetProperty("stage").GetString()).ToArray();
        Assert.That(stages, Is.EqualTo(new[] {"planning", "requirements", "design", "development", "testing", "release", "operations"}));
        var models = response.RootElement.GetProperty("models");
        Assert.That(models.GetProperty("codex").GetString(), Is.EqualTo("gpt-6-astra"));
        Assert.That(models.GetProperty("github-copilot").GetString(), Is.EqualTo("claude-haiku-4.5"));
    }

    public void AssertVersionHistory()
    {
        using var response = JsonDocument.Parse(api.ResponseBody);
        var artifacts = response.RootElement.GetProperty("artifacts").EnumerateArray().ToArray();
        Assert.That(artifacts.Select(item => item.GetProperty("version").GetInt32()), Is.EqualTo(new[] {2, 1}));
        var reviews = response.RootElement.GetProperty("reviews").EnumerateArray().ToArray();
        Assert.That(reviews.Length, Is.EqualTo(1));
        Assert.That(reviews[0].GetProperty("version").GetInt32(), Is.EqualTo(1));
        Assert.That(reviews[0].GetProperty("decision").GetString(), Is.EqualTo("approved"));
    }
}
