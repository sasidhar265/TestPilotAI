using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
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

        public void LoadQuotationRequest()
        {
            requestBody = null;
            response = null;
            var service = new QuotationRequestService(new ApprovedQuotationRequestStrategy());
            requestBody = service.BuildJson(
                Path.Combine(AppContext.BaseDirectory, "Input", "QuotationRequest.Json"));
        }

        public void LoadQuotationFixture(string name)
        {
            requestBody = null;
            response = null;
            requestBody = QuotationRequestBuilder.FromJson(ReadFixture(name).GetRawText()).BuildJson();
        }

        public void LoadQuotationEligibilityFixture(
            string fixture, string customerType, string productType, string eligibility)
        {
            requestBody = null;
            response = null;
            var row = ReadFixture(fixture).GetProperty("eligibilityCases").EnumerateArray()
                .Single(value => Matches(value, "customerType", customerType)
                    && Matches(value, "productType", productType)
                    && Matches(value, "eligibility", eligibility));
            requestBody = QuotationRequestBuilder.FromJson(row.GetProperty("request").GetRawText())
                .BuildJson();
        }

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
            var defaultPath = Path.Combine(AppContext.BaseDirectory, "Input", "TestData.Json");
            var json = !string.IsNullOrWhiteSpace(path) ? File.ReadAllText(path)
                : File.Exists(defaultPath) ? File.ReadAllText(defaultPath) : ApprovedFixtures.Json;
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

}
