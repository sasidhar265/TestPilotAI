using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using QualityLifecycle.Automation.Models;
using QualityLifecycle.Automation.Utilities;

namespace QualityLifecycle.Automation.Builders;

public static class KnowledgeAgentRequestBuilder
{
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web);

    public static JsonObject Definition(string fixture)
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "KnowledgeAgents.Json")));
        var model = data.RootElement.GetProperty(fixture).Deserialize<KnowledgeAgentModel>(Options)
            ?? throw new InvalidOperationException("Knowledge fixture could not be read.");
        return JsonSerializer.SerializeToNode(model, Options)!.AsObject();
    }

    public static JsonObject Review(int revision)
    {
        var data = JsonNode.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "KnowledgeAgents.Json")))!.AsObject();
        var review = data["review"]!.DeepClone().AsObject();
        review["revision"] = revision;
        return review;
    }

    public static HttpRequestMessage Build(HttpMethod method, string path, JsonObject? body = null,
        bool authenticated = true)
    {
        var request = new HttpRequestMessage(method, path);
        if (body is not null)
            request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json");
        if (authenticated)
            AuthenticationUtility.Apply(request);
        return request;
    }
}
