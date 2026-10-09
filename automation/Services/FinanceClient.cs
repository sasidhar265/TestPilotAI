namespace QualityLifecycle.Automation.Services;

public sealed class FinanceClient(HttpClient http)
{
    public Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token) =>
        http.SendAsync(request, token);
}
