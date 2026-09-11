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
