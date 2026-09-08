using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.DependencyInjection;

namespace Generated.StepDefinitions
{
    // ReqnRoll creates and disposes this context once per scenario through context injection.
    public sealed class ApiScenario : IDisposable
    {
        private readonly ApiClient client;
        private string requestBody;
        private ApiResponse response;

        public ApiScenario() : this(new ApiClient(ApiClientFactory.CreateClient())) { }

        internal ApiScenario(ApiClient client) { this.client = client; }

        public void LoadFixture(string name)
        {
            requestBody = null;
            response = null;
            var payload = ReadFixture(name);
            requestBody = payload.GetRawText();
        }

        private static JsonElement ReadFixture(string name)
        {
            var path = Environment.GetEnvironmentVariable("API_FIXTURE_FILE");
            var json = string.IsNullOrWhiteSpace(path)
                ? ApprovedFixtures.Json : File.ReadAllText(path);
            using var fixtures = JsonDocument.Parse(json);
            if (!fixtures.RootElement.TryGetProperty(name, out var payload))
                throw new InvalidOperationException($"Missing approved request fixture: {name}");
            return payload.Clone();
        }

        public void LoadEligibilityFixture(
            string fixture, string customerType, string productType, string eligibility)
        {
            requestBody = null;
            response = null;
            var source = ReadFixture(fixture);
            if (source.ValueKind != JsonValueKind.Object ||
                !source.TryGetProperty("eligibilityCases", out var cases) ||
                cases.ValueKind != JsonValueKind.Array)
                throw new InvalidOperationException(
                    $"Fixture '{fixture}' requires an eligibilityCases array of approved " +
                    "customerType, productType, eligibility and request records.");

            JsonElement? selected = null;
            foreach (var row in cases.EnumerateArray())
            {
                if (!Matches(row, "customerType", customerType) ||
                    !Matches(row, "productType", productType) ||
                    !Matches(row, "eligibility", eligibility)) continue;
                if (selected.HasValue)
                    throw new InvalidOperationException(
                        $"Fixture '{fixture}' contains duplicate eligibility combinations.");
                if (!row.TryGetProperty("request", out var request) ||
                    request.ValueKind != JsonValueKind.Object)
                    throw new InvalidOperationException(
                        $"Fixture '{fixture}' eligibility case requires an approved request object.");
                if (!Matches(request, "customerType", customerType) ||
                    !Matches(request, "productType", productType))
                    throw new InvalidOperationException(
                        $"Fixture '{fixture}' request does not match its customer/product combination.");
                selected = request;
            }
            if (!selected.HasValue)
                throw new InvalidOperationException(
                    $"Fixture '{fixture}' has no approved case for " +
                    $"customerType='{customerType}', productType='{productType}', " +
                    $"eligibility='{eligibility}'.");

            // Eligibility describes approved fixture data; it is not an invented request field
            // or a calculated business rule. Only the selected request is sent to the API.
            requestBody = selected.Value.GetRawText();
        }

        private static bool Matches(JsonElement value, string property, string expected) =>
            value.ValueKind == JsonValueKind.Object &&
            value.TryGetProperty(property, out var actual) &&
            actual.ValueKind == JsonValueKind.String &&
            string.Equals(actual.GetString(), expected, StringComparison.Ordinal);

        public Task SubmitConfiguredAsync()
        {
            return SendAsync(RequiredSetting("API_REQUEST_METHOD"),
                RequiredSetting("API_REQUEST_PATH"));
        }

        public async Task SendAsync(string method, string path)
        {
            if (requestBody == null)
                throw new InvalidOperationException("Load an approved request fixture first.");
            response = null;
            response = await client.SendAsync(method, path, requestBody, CancellationToken.None);
        }

        public void AssertStatus(int expected)
        {
            var actual = RequireResponse().Status;
            if (actual != expected)
                throw new InvalidOperationException($"Expected HTTP {expected}, received {actual}.");
        }

        public void AssertField(string path, string expected)
        {
            using var document = JsonDocument.Parse(RequireResponse().Body);
            var value = Field(document.RootElement, path);
            var actual = value.ValueKind == JsonValueKind.String
                ? value.GetString() : value.GetRawText();
            if (!string.Equals(actual, expected, StringComparison.Ordinal))
                throw new InvalidOperationException($"Response field '{path}' did not match.");
        }

        public void AssertDecimal(string path, decimal expected)
        {
            using var document = JsonDocument.Parse(RequireResponse().Body);
            var value = Field(document.RootElement, path);
            var actual = value.ValueKind == JsonValueKind.String
                ? decimal.Parse(value.GetString(), NumberStyles.Number, CultureInfo.InvariantCulture)
                : value.GetDecimal();
            if (actual != expected)
                throw new InvalidOperationException($"Response decimal field '{path}' did not match.");
        }

        public void AssertFieldPresent(string path)
        {
            using var document = JsonDocument.Parse(RequireResponse().Body);
            var value = Field(document.RootElement, path);
            if (value.ValueKind == JsonValueKind.Null ||
                (value.ValueKind == JsonValueKind.String && string.IsNullOrWhiteSpace(value.GetString())))
                throw new InvalidOperationException($"Response field '{path}' is empty.");
        }

        private static JsonElement Field(JsonElement value, string path)
        {
            foreach (var segment in path.Split('.'))
            {
                if (value.ValueKind != JsonValueKind.Object ||
                    !value.TryGetProperty(segment, out var next))
                    throw new InvalidOperationException($"Response field '{path}' is missing.");
                value = next;
            }
            return value;
        }

        private ApiResponse RequireResponse() => response ??
            throw new InvalidOperationException("Send a request before asserting its response.");

        internal static string RequiredSetting(string name)
        {
            var value = Environment.GetEnvironmentVariable(name);
            if (string.IsNullOrWhiteSpace(value))
                throw new InvalidOperationException($"Configure {name} before running API scenarios.");
            return value;
        }

        public void Dispose() => client.Dispose();
    }

    public sealed class ApiResponse
    {
        public int Status { get; }
        public string Body { get; }
        public IReadOnlyDictionary<string, string> Headers { get; }

        public ApiResponse(int status, string body, IReadOnlyDictionary<string, string> headers)
        { Status = status; Body = body; Headers = headers; }
    }

    public sealed class ApiClient : IDisposable
    {
        private readonly HttpClient http;
        public ApiClient(HttpClient http) { this.http = http; }

        public async Task<ApiResponse> SendAsync(
            string method, string path, string body, CancellationToken cancellationToken)
        {
            // Resolve against the configured API only, including when paths contain a leading slash.
            if (http.BaseAddress == null)
                throw new InvalidOperationException("Configure API_BASE_URL before sending requests.");
            var target = new Uri(http.BaseAddress, path);
            if (target.GetLeftPart(UriPartial.Authority) !=
                http.BaseAddress.GetLeftPart(UriPartial.Authority))
                throw new InvalidOperationException("Request path must use the configured API origin.");
            using var request = new HttpRequestMessage(new HttpMethod(method), target);
            request.Content = new StringContent(body, Encoding.UTF8, "application/json");
            using var response = await http.SendAsync(request, cancellationToken);
            var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
            var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var header in response.Headers)
                headers[header.Key] = string.Join(",", header.Value);
            foreach (var header in response.Content.Headers)
                headers[header.Key] = string.Join(",", header.Value);
            return new ApiResponse((int)response.StatusCode, responseBody, headers);
        }

        public void Dispose() => http.Dispose();
    }

    internal static class ApiClientFactory
    {
        // Only transport infrastructure is shared. Requests and results belong to ApiScenario.
        private static readonly Lazy<ServiceProvider> Services = new Lazy<ServiceProvider>(() =>
        {
            var services = new ServiceCollection();
            services.AddHttpClient("GeneratedApi", client =>
            {
                client.BaseAddress = new Uri(ApiScenario.RequiredSetting("API_BASE_URL"));
                var token = Environment.GetEnvironmentVariable("API_BEARER_TOKEN");
                if (!string.IsNullOrWhiteSpace(token))
                    client.DefaultRequestHeaders.Authorization =
                        new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", token);
            }).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
            { AllowAutoRedirect = false, UseCookies = false });
            return services.BuildServiceProvider();
        });

        public static HttpClient CreateClient() =>
            Services.Value.GetRequiredService<IHttpClientFactory>().CreateClient("GeneratedApi");
    }
}
