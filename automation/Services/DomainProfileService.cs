using System.Text.Json;
using System.Text.Json.Nodes;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;

namespace QualityLifecycle.Automation.Services;

public sealed class DomainProfileService : IDisposable
{
    private readonly ApiService api = new();
    private string? identifier;
    private string original = string.Empty;
    private int originalSelectionRevision;
    private int revision;
    private const string AdminPath = "/api/admin/domain-profiles";

    private async Task Send(HttpRequestMessage request)
    {
        using (request)
            await api.RequestAsync(request);
    }

    private async Task<(string Profile, int Revision)> Selection()
    {
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Get, "/api/domain-profiles"));
        using var document = JsonDocument.Parse(api.ResponseBody);
        var selection = document.RootElement.GetProperty("selection");
        return (selection.GetProperty("profile").GetString()!, selection.GetProperty("revision").GetInt32());
    }

    public async Task Create()
    {
        (original, originalSelectionRevision) = await Selection();
        var body = DomainProfileRequestBuilder.Definition();
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post, AdminPath, body));
        if (api.Response!.IsSuccessStatusCode)
        {
            using var document = JsonDocument.Parse(api.ResponseBody);
            identifier = document.RootElement.GetProperty("id").GetString();
            revision = document.RootElement.GetProperty("revision").GetInt32();
        }
    }

    public Task Activate() => Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Put,
        AdminPath + "/selection", new JsonObject { ["profile"] = identifier, ["expected_revision"] = originalSelectionRevision }));

    public Task StaleSelection() => Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Put,
        AdminPath + "/selection", new JsonObject { ["profile"] = original, ["expected_revision"] = originalSelectionRevision }));

    public Task Invalid(string variant)
    {
        var body = DomainProfileRequestBuilder.Definition();
        var variants = new Dictionary<string, Action<JsonObject>>
        {
            ["builtin"] = item => item["id"] = "testpilot",
            ["model"] = item => item["model"] = "account-default",
            ["baseline"] = item => item["baseline"] = new JsonObject { ["sources"] = new JsonArray(new JsonObject { ["id"] = "incomplete-source" }) }
        };
        variants[variant](body);
        return Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post, AdminPath, body));
    }

    public Task StaleUpdate()
    {
        var body = DomainProfileRequestBuilder.Definition();
        body["id"] = identifier;
        return Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post, AdminPath, body));
    }

    public Task AnonymousCreate() => Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post,
        AdminPath, DomainProfileRequestBuilder.Definition(), false));

    public void AssertStatus(int expected) => Assert.That((int)api.Response!.StatusCode, Is.EqualTo(expected));

    public async Task AssertOriginal() => Assert.That((await Selection()).Profile, Is.EqualTo(original));

    public async Task AssertActive()
    {
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Get, "/api/health"));
        using var health = JsonDocument.Parse(api.ResponseBody);
        Assert.That(health.RootElement.GetProperty("agent_profile").GetString(), Is.EqualTo(identifier));
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Get, "/api/finance/domain-pack"));
        AssertStatus(503);
    }

    public async Task Cleanup()
    {
        if (identifier is null)
            return;
        var selection = await Selection();
        if (selection.Profile == identifier)
        {
            await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Put, AdminPath + "/selection",
                new JsonObject { ["profile"] = original, ["expected_revision"] = selection.Revision }));
            AssertStatus(200);
        }
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Delete,
            $"{AdminPath}/{identifier}?expected_revision={revision}"));
        AssertStatus(200);
    }

    public void Dispose() => api.Dispose();
}
