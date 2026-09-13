using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace QualityLifecycle.Automation.Builders;

public static class WorkflowRequestBuilder
{
    public static HttpRequestMessage Build(string fixture)
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "Workflow.Json")));
        var input = data.RootElement.GetProperty(fixture);
        var request = new HttpRequestMessage(HttpMethod.Post,
            "/api/workflow/" + input.GetProperty("endpoint").GetString())
        {
            Content = new StringContent(input.GetProperty("body").GetRawText(), Encoding.UTF8,
                "application/json")
        };
        var token = Environment.GetEnvironmentVariable("API_AUTH_TOKEN");
        if (!string.IsNullOrWhiteSpace(token))
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return request;
    }
}
