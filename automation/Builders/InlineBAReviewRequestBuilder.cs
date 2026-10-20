using System.Net.Http.Json;
using System.Text.Json.Nodes;

namespace QualityLifecycle.Automation.Builders;

public static class InlineBAReviewRequestBuilder
{
    public static JsonObject Data => JsonNode.Parse(File.ReadAllText(
        Path.Combine(AppContext.BaseDirectory, "Input", "InlineBAReview.Json")))!.AsObject();
    public static JsonObject Case(string name) => Data["cases"]!.AsArray()
        .Single(item => item!["name"]!.GetValue<string>() == name)!.DeepClone().AsObject();
    public static HttpRequestMessage Post(string path, object payload) => new(HttpMethod.Post,
        "/api/sdlc/" + path) { Content = JsonContent.Create(payload) };
    public static HttpRequestMessage Source(string project, string name, int version = 0)
    {
        var document = Case(name)["document"]!.GetValue<string>();
        return Post($"projects/{project}/artifacts/requirements-input", new {
            content = new { document, source_request = new { description = document, llm_model = "codex" } },
            base_version = version, links = Array.Empty<object>()
        });
    }
    public static HttpRequestMessage Start(string project, int baseline = 1, bool force = false) =>
        Post($"projects/{project}/ba-reviews", new { baseline, force });
    public static HttpRequestMessage SupportingRecords(string project) =>
        new(HttpMethod.Get, $"/api/sdlc/projects/{project}/work-items");
    public static HttpRequestMessage EditSupportingRecord(string project, JsonObject record)
    {
        var fields = new[] { "id", "kind", "description", "status", "priority", "estimate",
            "assignee", "sprint", "acceptance_criteria", "links", "references" };
        var payload = new JsonObject();
        foreach (var field in fields) payload[field] = record[field]?.DeepClone();
        payload["base_version"] = record["version"]!.DeepClone();
        payload["title"] = Data["supporting_records"]!["edited_title"]!.DeepClone();
        return Post($"projects/{project}/work-items", payload);
    }
    public static HttpRequestMessage BusinessDocument(string project, string document) =>
        new(HttpMethod.Get, $"/api/sdlc/projects/{project}/ba-documents?document={Uri.EscapeDataString(document)}");
    public static HttpRequestMessage BacklogStory(string project, string requirement, string state = "draft")
    {
        var payload = Data["backlog_story"]!.DeepClone().AsObject();
        payload["links"] = new JsonArray(requirement);
        payload["status"] = state;
        return Post($"projects/{project}/work-items", payload);
    }
    public static HttpRequestMessage Decision(string project, JsonObject run, string action) =>
        Post($"projects/{project}/ba-reviews/{run["id"]!.GetValue<string>()}/decisions", new {
            revision = run["revision"]!.GetValue<int>(),
            finding_id = run["output"]!["findings"]![0]!["finding_id"]!.GetValue<string>(),
            finding_version = run["output"]!["findings"]![0]!["version"]!.GetValue<int>(), action,
            proposed_text = Data["edited_proposal"]!.GetValue<string>(),
            comment = Data["comment"]!.GetValue<string>()
        });
    public static HttpRequestMessage RevisedBRD(string project, JsonObject run) =>
        Post($"projects/{project}/ba-reviews/{run["id"]!.GetValue<string>()}/revised-brd", new {
            revision = run["revision"]!.GetValue<int>()
        });
    public static HttpRequestMessage Signoff(string project, JsonObject run) =>
        Post($"projects/{project}/ba-reviews/{run["id"]!.GetValue<string>()}/signoff", new {
            revision = run["revision"]!.GetValue<int>(), comment = Data["comment"]!.GetValue<string>()
        });
}
