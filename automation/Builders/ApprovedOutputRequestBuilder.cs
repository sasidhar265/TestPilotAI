using System.Text;
using System.Text.Json;
using QualityLifecycle.Automation.Utilities;

namespace QualityLifecycle.Automation.Builders;

public static class ApprovedOutputRequestBuilder
{
    public static JsonElement Input()
    {
        using var input = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "ApprovedOutputs.Json")));
        return input.RootElement.Clone();
    }

    public static HttpRequestMessage Approve()
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/output/accept")
        {
            Content = new StringContent(Input().GetRawText(), Encoding.UTF8, "application/json")
        };
        AuthenticationUtility.Apply(request);
        return request;
    }

    public static HttpRequestMessage Read(string path)
    {
        var request = new HttpRequestMessage(HttpMethod.Get, path);
        AuthenticationUtility.Apply(request);
        return request;
    }
}
