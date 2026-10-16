using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace QualityLifecycle.Automation.Builders;

public static class LifecycleRequestBuilder
{
    public static JsonObject Fixture(string file, string name) =>
        JsonNode.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Input", file)))![name]!.DeepClone().AsObject();

    public static HttpRequestMessage Post(string path, object payload) =>
        new(HttpMethod.Post, "/api/sdlc/" + path)
        {
            Content = JsonContent.Create(payload)
        };

    public static HttpRequestMessage Annotation(string project, string item, string fixture) =>
        Post($"projects/{project}/work-items/{item}/annotations", Fixture("Lifecycle.Json", fixture));

    public static HttpRequestMessage Detail(string project, string item) =>
        new(HttpMethod.Get, $"/api/sdlc/projects/{project}/work-items/{item}/detail");

    public static HttpRequestMessage Decision(string project, int revision, string fixture)
    {
        var body = Fixture("Lifecycle.Json", fixture);
        body["revision"] = revision;
        return Post($"projects/{project}/transitions", body);
    }

    public static HttpRequestMessage Evidence(string project, int revision, string kind)
    {
        var body = Fixture("Lifecycle.Json", "evidence");
        body["revision"] = revision;
        body["kind"] = kind;
        return Post($"projects/{project}/evidence", body);
    }
}
