using System.Net.Http.Headers;
using System.Text;
using System.Text.Json.Nodes;

namespace QualityLifecycle.Automation.Builders;

public static class CodeGenerationRequestBuilder
{
    private static readonly IReadOnlyDictionary<string, Action<JsonObject>> Reports =
        new Dictionary<string, Action<JsonObject>>
        {
            ["passed"] = report => report["passed"] = true,
            ["failed"] = report => report["passed"] = false,
            ["inconsistent"] = report => report["findings"] = JsonNode.Parse(
                """[{"dimension":"coverage","severity":"error","message":"Missing required case","test_case_ids":["TC-HEALTH-001"]}]""")
        };

    public static HttpRequestMessage Build(string validation)
    {
        var data = JsonNode.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "CodeGeneration.Json")))!.AsObject();
        Reports[validation](data["validation"]!.AsObject());
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/step-definitions/reqnroll")
        {
            Content = new StringContent(data.ToJsonString(), Encoding.UTF8, "application/json")
        };
        var token = Environment.GetEnvironmentVariable("API_AUTH_TOKEN");
        if (!string.IsNullOrWhiteSpace(token))
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return request;
    }
}
