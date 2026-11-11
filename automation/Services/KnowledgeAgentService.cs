using System.Text.Json;
using System.Text.Json.Nodes;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;

namespace QualityLifecycle.Automation.Services;

public sealed class KnowledgeAgentService : IDisposable
{
    private readonly ApiService api = new();
    private string? agentId;
    private int latestRevision;
    private const string AdminPath = "/api/admin/knowledge-agents";

    private async Task Send(HttpRequestMessage request, bool capture = false)
    {
        using (request)
            await api.RequestAsync(request);
        if (capture && api.Response!.IsSuccessStatusCode)
        {
            using var document = JsonDocument.Parse(api.ResponseBody);
            agentId = document.RootElement.GetProperty("id").GetString();
            latestRevision = document.RootElement.GetProperty("latest").GetProperty("revision").GetInt32();
        }
    }

    public Task Create(string fixture) => Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post,
        AdminPath, KnowledgeAgentRequestBuilder.Definition(fixture)), true);

    public Task UnauthenticatedCreate() => Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post,
        AdminPath, KnowledgeAgentRequestBuilder.Definition("reference-contributor"), false));

    public Task CreateWithModelOverride()
    {
        var body = KnowledgeAgentRequestBuilder.Definition("reference-contributor");
        body["model"] = "account-default";
        return Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post, AdminPath, body));
    }

    public Task Update(string fixture, int expected)
    {
        var body = KnowledgeAgentRequestBuilder.Definition(fixture);
        body["expected_revision"] = expected;
        return Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Put, $"{AdminPath}/{agentId}", body), true);
    }

    public Task Review(int revision) => Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post,
        $"{AdminPath}/{agentId}/review", KnowledgeAgentRequestBuilder.Review(revision)), true);

    public Task ReviewWithoutApproval(int revision)
    {
        var body = KnowledgeAgentRequestBuilder.Review(revision);
        body["approve_reference_use"] = false;
        return Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post,
            $"{AdminPath}/{agentId}/review", body));
    }

    public Task Action(string action, int revision) => Send(KnowledgeAgentRequestBuilder.Build(
        HttpMethod.Post, $"{AdminPath}/{agentId}/{action}", new JsonObject { ["revision"] = revision }), true);

    public async Task ValidateExportImport()
    {
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Get,
            $"/api/knowledge-agents/{agentId}/export"));
        var exported = JsonNode.Parse(api.ResponseBody)!.AsObject();
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post,
            $"{AdminPath}/import/validate", exported));
    }

    public Task ValidateImportWithModelOverride()
    {
        var body = KnowledgeAgentRequestBuilder.Definition("reference-contributor");
        body["model"] = "account-default";
        return Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Post,
            $"{AdminPath}/import/validate", body));
    }

    public Task ValidateUnsupportedImport() => Send(KnowledgeAgentRequestBuilder.Build(
        HttpMethod.Post, $"{AdminPath}/import/validate", new JsonObject { ["schema_version"] = 99 }));

    public void AssertImportDraft()
    {
        using var document = JsonDocument.Parse(api.ResponseBody);
        Assert.That(document.RootElement.GetProperty("status").GetString(), Is.EqualTo("draft"));
        var definition = document.RootElement.GetProperty("definition");
        Assert.That(definition.TryGetProperty("id", out _), Is.False);
        Assert.That(definition.TryGetProperty("status", out _), Is.False);
        Assert.That(definition.GetProperty("stages")[0].GetString(), Is.EqualTo("stories"));
    }

    public void AssertStatus(int expected) => Assert.That((int)api.Response!.StatusCode, Is.EqualTo(expected));

    public async Task AssertActive(int expected)
    {
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Get, "/api/knowledge-agents"));
        using var document = JsonDocument.Parse(api.ResponseBody);
        var agent = document.RootElement.GetProperty("agents").EnumerateArray()
            .Single(item => item.GetProperty("id").GetString() == agentId);
        var published = agent.GetProperty("published");
        var actual = published.ValueKind == JsonValueKind.Null ? 0 : published.GetProperty("revision").GetInt32();
        Assert.That(actual, Is.EqualTo(expected));
    }

    public async Task AssertCatalog(bool included)
    {
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Get, "/api/agents"));
        using var document = JsonDocument.Parse(api.ResponseBody);
        var found = document.RootElement.EnumerateArray()
            .Any(item => item.GetProperty("id").GetString() == agentId);
        Assert.That(found, Is.EqualTo(included));
    }

    public async Task Cleanup()
    {
        if (agentId is null)
            return;
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Get, "/api/knowledge-agents"));
        using var document = JsonDocument.Parse(api.ResponseBody);
        var agent = document.RootElement.GetProperty("agents").EnumerateArray()
            .Single(item => item.GetProperty("id").GetString() == agentId);
        var published = agent.GetProperty("published");
        if (published.ValueKind != JsonValueKind.Null)
            await Action("withdraw", published.GetProperty("revision").GetInt32());
        await Send(KnowledgeAgentRequestBuilder.Build(HttpMethod.Delete,
            $"{AdminPath}/{agentId}?expected_revision={latestRevision}"));
        AssertStatus(200);
    }

    public void Dispose() => api.Dispose();
}
