using System.Text;
using System.Text.Json;
using QualityLifecycle.Automation.Utilities;

namespace QualityLifecycle.Automation.Builders;

public static class SdlcRequestBuilder
{
    public static HttpRequestMessage Get(string path)
    {
        var request = new HttpRequestMessage(HttpMethod.Get, "/api/sdlc/" + path);
        AuthenticationUtility.Apply(request);
        return request;
    }

    public static HttpRequestMessage Post(string path, string fixture)
    {
        using var input = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "SDLC.Json")));
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/sdlc/" + path)
        {
            Content = new StringContent(input.RootElement.GetProperty(fixture).GetRawText(),
                Encoding.UTF8, "application/json")
        };
        AuthenticationUtility.Apply(request);
        return request;
    }
}
