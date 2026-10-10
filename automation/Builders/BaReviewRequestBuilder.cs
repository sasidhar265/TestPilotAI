using System.Text;
using QualityLifecycle.Automation.Models;
using QualityLifecycle.Automation.Utilities;
namespace QualityLifecycle.Automation.Builders;
public static class BaReviewRequestBuilder
{
    public static HttpRequestMessage Build(BaReviewFixtureModel fixture)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/workflow/ba-review")
        { Content = new StringContent(fixture.Request.GetRawText(), Encoding.UTF8, "application/json") };
        AuthenticationUtility.Apply(request);
        return request;
    }
}
