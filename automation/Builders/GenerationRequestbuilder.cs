using System.Net.Http.Headers;
using System.Net.Http.Json;
using QualityLifecycle.Automation.Models;
namespace QualityLifecycle.Automation.Builders;

public static class GenerationRequestBuilder
{
    public static HttpRequestMessage Build(string description, bool authenticated)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/generate")
        { Content = JsonContent.Create(new GenerationRequestModel(description)) };
        var token = Environment.GetEnvironmentVariable("API_AUTH_TOKEN");
        if (authenticated && !string.IsNullOrWhiteSpace(token))
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return request;
    }
}
