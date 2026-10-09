using System.Text;
using QualityLifecycle.Automation.Models;
using QualityLifecycle.Automation.Utilities;
namespace QualityLifecycle.Automation.Builders;

public static class FinanceRequestBuilder
{
    public static HttpRequestMessage Catalogue()
    {
        var request = new HttpRequestMessage(HttpMethod.Get, "/api/finance/domain-pack");
        AuthenticationUtility.Apply(request);
        return request;
    }
    public static HttpRequestMessage Calculation(FinanceFixtureModel fixture)
    {
        var request = new HttpRequestMessage(HttpMethod.Post, "/api/finance/calculations")
        { Content = new StringContent(fixture.Request.GetRawText(), Encoding.UTF8, "application/json") };
        AuthenticationUtility.Apply(request);
        return request;
    }
}
