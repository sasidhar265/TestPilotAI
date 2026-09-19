using System.Text;
using Allure.Net.Commons;
using QualityLifecycle.Automation.Utilities;
namespace QualityLifecycle.Automation.Services;

public sealed class ApiService : IDisposable
{
    private readonly HttpClient http = new() { BaseAddress = new Uri(ConfigurationUtility.BaseUrl) };
    public HttpResponseMessage? Response
    {
        get; private set;
    }
    public string ResponseBody { get; private set; } = string.Empty;
    public async Task RequestAsync(HttpRequestMessage request)
    {
        var requestBody = request.Content is null
            ? string.Empty
            : await request.Content.ReadAsStringAsync();
        AddAttachment("API request", FormatRequest(request, requestBody));
        Response?.Dispose();
        Response = await http.SendAsync(request);
        ResponseBody = await Response.Content.ReadAsStringAsync();
        AddAttachment("API response", FormatResponse(Response, ResponseBody));
    }

    private static void AddAttachment(string name, string content) =>
        AllureApi.AddAttachment(name, "text/plain", Encoding.UTF8.GetBytes(content), ".txt");

    private static string FormatRequest(HttpRequestMessage request, string body) =>
        $"{request.Method} {request.RequestUri}\n"
        + FormatHeaders(request.Headers)
        + (request.Content is null ? string.Empty : FormatHeaders(request.Content.Headers))
        + $"\n{Redact(body)}";

    private static string FormatResponse(HttpResponseMessage response, string body) =>
        $"HTTP {(int)response.StatusCode} {response.ReasonPhrase}\n"
        + FormatHeaders(response.Headers)
        + FormatHeaders(response.Content.Headers)
        + $"\n{Redact(body)}";

    private static string FormatHeaders(IEnumerable<KeyValuePair<string, IEnumerable<string>>> headers) =>
        string.Join("\n", headers.Select(header => $"{header.Key}: {Redact(string.Join(", ", header.Value))}"));

    private static string Redact(string value)
    {
        foreach (var name in new[] { "API_AUTH_TOKEN", "API_SESSION_COOKIE", "APP_PASSWORD", "OPENAI_API_KEY", "GEMINI_API_KEY", "COPILOT_GITHUB_TOKEN" })
        {
            var secret = ConfigurationUtility.GetValue(name);
            if (!string.IsNullOrWhiteSpace(secret)) value = value.Replace(secret, "[REDACTED]", StringComparison.Ordinal);
        }
        return value;
    }

    public void Dispose()
    {
        Response?.Dispose();
        http.Dispose();
    }
}
