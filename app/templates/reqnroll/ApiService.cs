using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Allure.Net.Commons;
using Microsoft.Extensions.DependencyInjection;

namespace Generated.StepDefinitions
{
    public sealed class ApiClient : IDisposable
    {
        private readonly HttpClient http;
        public ApiClient(HttpClient http)
        {
            this.http = http;
        }

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
            AllureApi.AddAttachment(
                "API request",
                "text/plain",
                Encoding.UTF8.GetBytes($"{request.Method} {request.RequestUri}\n\n{body}"),
                ".txt");
            using var response = await http.SendAsync(request, cancellationToken);
            var responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
            var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var header in response.Headers)
                headers[header.Key] = string.Join(",", header.Value);
            foreach (var header in response.Content.Headers)
                headers[header.Key] = string.Join(",", header.Value);
            AllureApi.AddAttachment(
                "API response",
                "text/plain",
                Encoding.UTF8.GetBytes($"HTTP {(int)response.StatusCode} {response.ReasonPhrase}\n\n{responseBody}"),
                ".txt");
            return new ApiResponse((int)response.StatusCode, responseBody, headers);
        }

        public void Dispose() => http.Dispose();
    }

}
