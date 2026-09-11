using QualityLifecycle.Automation.Utilities;
namespace QualityLifecycle.Automation.Services;

public sealed class ApiService : IDisposable
{
    private readonly HttpClient http = new() { BaseAddress = new Uri(ConfigurationUtility.BaseUrl) };
    public HttpResponseMessage? Response { get; private set; }
    public string ResponseBody { get; private set; } = string.Empty;
    public async Task RequestAsync(HttpRequestMessage request)
    {
        Response?.Dispose();
        Response = await http.SendAsync(request);
        ResponseBody = await Response.Content.ReadAsStringAsync();
    }

    public void Dispose() { Response?.Dispose(); http.Dispose(); }
}
