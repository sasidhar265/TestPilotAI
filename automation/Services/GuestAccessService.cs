using System.Net;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;
using QualityLifecycle.Automation.Utilities;
namespace QualityLifecycle.Automation.Services;

public sealed class GuestAccessService : IDisposable
{
    private readonly HttpClient http = new(new HttpClientHandler
    {
        AllowAutoRedirect = false,
        UseCookies = true,
        CookieContainer = new CookieContainer()
    }) { BaseAddress = new Uri(ConfigurationUtility.BaseUrl) };
    private HttpStatusCode status;

    public async Task EnterAsync()
    {
        using var request = GuestAccessRequestBuilder.Entry();
        using var response = await http.SendAsync(request);
        Assert.That(response.StatusCode, Is.EqualTo(HttpStatusCode.SeeOther),
            "Configure a future TEMPORARY_GUEST_ACCESS_UNTIL and browser login on the isolated target.");
    }

    public async Task RequestProtectedAsync(string name, string method)
    {
        using var request = GuestAccessRequestBuilder.Protected(name, method);
        using var response = await http.SendAsync(request);
        status = response.StatusCode;
    }

    public async Task RequestPreviewAsync()
    {
        using var request = GuestAccessRequestBuilder.Preview();
        using var response = await http.SendAsync(request);
        status = response.StatusCode;
        Assert.That(await response.Content.ReadAsStringAsync(), Does.Contain("data-guest=\"true\""));
    }

    public void AssertStatus(int expected) => Assert.That((int)status, Is.EqualTo(expected));
    public void Dispose() => http.Dispose();
}
