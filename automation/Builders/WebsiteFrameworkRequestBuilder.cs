using System.Text;
using System.Text.Json;
using QualityLifecycle.Automation.Utilities;
namespace QualityLifecycle.Automation.Builders;
public static class WebsiteFrameworkRequestBuilder
{
    public static HttpRequestMessage Build(string fixture)
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "WebsiteFramework.Json")));
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/agent/run")
        {
            Content = new StringContent(data.RootElement.GetProperty(fixture).GetRawText(),
                Encoding.UTF8, "application/json")
        };
        AuthenticationUtility.Apply(request);
        return request;
    }
}
