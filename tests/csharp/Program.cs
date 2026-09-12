using System;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Generated.StepDefinitions;

internal static class Program
{
    private static void Fails(Action action)
    {
        try
        {
            action();
        }
        catch (InvalidOperationException) { return; }
        throw new Exception("Expected the assertion or precondition to fail.");
    }

    public static async Task Main()
    {
        using var handler = new RecordingHandler();
        using var http = new HttpClient(handler) { BaseAddress = new Uri("https://example.test/") };
        using var api = new ApiScenario(new ApiClient(http));
        Fails(() => api.AssertStatus(201));
        Fails(() => api.LoadFixture("missing"));
        api.LoadFixture("valid");
        await api.SendAsync("POST", "/quotes");
        if (handler.Method != "POST" || handler.Path != "/quotes" ||
            !handler.Body.Contains("12.30"))
            throw new Exception("Wrong request sent.");
        api.AssertStatus(201);
        api.AssertField("quote.id", "q-1");
        api.AssertFieldPresent("quote.id");
        api.AssertDecimal("quote.total", 12.30m);
        api.AssertDecimal("quote.numeric", -12.30m);
        Fails(() => api.AssertStatus(400));
        Fails(() => api.AssertField("quote.id", "wrong"));
        Fails(() => api.AssertFieldPresent("missing"));
        Fails(() => api.AssertFieldPresent("empty"));
        Fails(() => api.AssertDecimal("quote.total", 12.31m));
        api.LoadFixture("valid");
        Fails(() => api.AssertStatus(201)); // Loading a new request clears the prior response.
        try
        {
            await api.SendAsync("POST", "https://other.test/quotes");
        }
        catch (InvalidOperationException) { goto originRejected; }
        throw new Exception("Cross-origin request was accepted.");
    originRejected:
        handler.Status = HttpStatusCode.BadRequest;
        await api.SendAsync("POST", "/quotes");
        api.AssertStatus(400); // Negative HTTP responses remain available for assertions.
        using var isolated = new ApiScenario(new ApiClient(new HttpClient(handler)));
        Fails(() => isolated.AssertStatus(400));

        // Exercise the actual generated four-parameter binding from the reported failure.
        var bindings = new APIStepDefinition(api);
        var eligibilityStep = typeof(APIStepDefinition).GetMethods()
            .Single(method => method.Name.StartsWith("Given") && method.GetParameters().Length == 4);
        eligibilityStep.Invoke(bindings,
            new object[] { "\"catalogue\"", "\"private individual\"", "\"PCP\"", "\"eligible\"" });
        await api.SendAsync("POST", "/quotes");
        using (var payload = JsonDocument.Parse(handler.Body))
        {
            if (payload.RootElement.GetProperty("customerType").GetString() != "private individual" ||
                payload.RootElement.GetProperty("productType").GetString() != "PCP" ||
                payload.RootElement.GetProperty("amount").GetString() != "12.30" ||
                payload.RootElement.TryGetProperty("eligibility", out _) ||
                payload.RootElement.TryGetProperty("eligibilityCases", out _))
                throw new Exception("Eligibility setup sent incorrect request data.");
        }
        eligibilityStep.Invoke(bindings,
            new object[] { "catalogue", "limited company", "HP", "ineligible" });
        await api.SendAsync("POST", "/quotes");
        if (!handler.Body.Contains("15.60"))
            throw new Exception("Wrong eligibility row selected.");
        Fails(() => api.LoadEligibilityFixture("catalogue", "private individual", "PCP", "unknown"));
        Fails(() => api.AssertStatus(400));
        Fails(() => api.SendAsync("POST", "/quotes").GetAwaiter().GetResult());
        Fails(() => api.LoadEligibilityFixture("duplicate", "private individual", "PCP", "eligible"));
        Fails(() => api.LoadEligibilityFixture("inconsistent", "private individual", "PCP", "eligible"));
        Fails(() => api.LoadEligibilityFixture("valid", "private individual", "PCP", "eligible"));
        await QuotationChecks.Run(api, handler);
        Console.WriteLine("Generated C# runtime checks passed.");
    }
}

internal sealed class RecordingHandler : HttpMessageHandler
{
    public string Method;
    public string Path;
    public string Body;
    public HttpStatusCode Status = HttpStatusCode.Created;

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request, CancellationToken cancellationToken)
    {
        Method = request.Method.Method;
        Path = request.RequestUri.AbsolutePath;
        Body = await request.Content.ReadAsStringAsync(cancellationToken);
        return new HttpResponseMessage(Status)
        {
            Content = new StringContent(
                "{\"quote\":{\"id\":\"q-1\",\"total\":\"12.30\",\"numeric\":-12.30},\"empty\":null}")
        };
    }
}
