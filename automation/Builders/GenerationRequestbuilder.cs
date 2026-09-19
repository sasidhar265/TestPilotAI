using QualityLifecycle.Automation.Utilities;
using System.Net.Http.Json;
using QualityLifecycle.Automation.Models;
namespace QualityLifecycle.Automation.Builders;

public static class GenerationRequestBuilder
{
    public static HttpRequestMessage Build(string description, bool authenticated)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/generate")
        {
            Content = JsonContent.Create(new GenerationRequestModel(description))
        };
        if (authenticated) AuthenticationUtility.Apply(request);
        return request;
    }
}
