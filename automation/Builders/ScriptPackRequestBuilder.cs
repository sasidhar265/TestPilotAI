using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace QualityLifecycle.Automation.Builders;

public static class ScriptPackRequestBuilder
{
    public static JsonElement Input(string fixture)
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "ScriptPacks.Json")));
        return data.RootElement.GetProperty(fixture).Clone();
    }

    public static HttpRequestMessage Build(string fixture, string action)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/script-packs/" + action)
        {
            Content = new StringContent(Input(fixture).GetRawText(), Encoding.UTF8, "application/json")
        };
        var token = Environment.GetEnvironmentVariable("API_AUTH_TOKEN");
        if (!string.IsNullOrWhiteSpace(token))
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return request;
    }
}
