using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Generated.StepDefinitions;

internal static class QuotationChecks
{
    private static void Equal(string expected, string actual)
    {
        if (!JsonNode.DeepEquals(JsonNode.Parse(expected), JsonNode.Parse(actual)))
            throw new Exception("Quotation wire payload differs from the supplied contract.");
    }

    private static void Reject(string json)
    {
        try { QuotationRequestBuilder.FromJson(json).Build(); }
        catch (JsonException) { return; }
        throw new Exception("Unknown or missing quotation fields were accepted.");
    }

    public static async Task Run(ApiScenario api, RecordingHandler handler)
    {
        var path = Path.Combine(AppContext.BaseDirectory, "Input", "QuotationRequest.Json");
        var supplied = File.ReadAllText(path);
        var builder = QuotationRequestBuilder.FromFile(path);
        Equal(supplied, builder.BuildJson());
        var original = builder.Build();
        var changed = builder.WithDeposit(1234.567890123456789m).WithTerm(48).Build();
        if (original.Parameters.Deposit != 5000m || original.Parameters.Term != 36
            || changed.Parameters.Deposit != 1234.567890123456789m || changed.Parameters.Term != 48
            || changed.Vehicle.VehicleRegstrationDate != "2023-01-01"
            || changed.Outlet.Code != "OUTLET001")
            throw new Exception("Builder changes leaked into another request or lost precision.");
        Equal(supplied, QuotationRequestBuilder.FromFile(path).BuildJson());
        var approved = new QuotationRequestService(new ApprovedQuotationRequestStrategy());
        Equal(supplied, approved.BuildJson(path));
        var configured = new QuotationRequestService(new ConfiguredQuotationRequestStrategy(
            value => value.WithDeposit(1234.567890123456789m).WithTerm(48)));
        Equal(JsonSerializer.Serialize(changed), configured.BuildJson(path));

        var extra = JsonNode.Parse(supplied);
        extra["customerType"] = "unsupported";
        Reject(extra.ToJsonString());
        extra = JsonNode.Parse(supplied);
        extra["Vehicle"]["invented"] = "unsupported";
        Reject(extra.ToJsonString());
        Reject(supplied.Replace("VehicleRegstrationDate", "VehicleRegistrationDate"));
        Reject("{}");

        api.LoadQuotationRequest();
        await api.SendAsync("POST", "/configured-test-endpoint");
        Equal(supplied, handler.Body);
        try { api.LoadQuotationFixture("valid"); }
        catch (JsonException) { }
        try { await api.SendAsync("POST", "/configured-test-endpoint"); }
        catch (InvalidOperationException)
        {
            Console.WriteLine("Quotation builder, strategies and wire-payload checks passed.");
            return;
        }
        throw new Exception("A failed quotation build reused the previous request.");
    }
}
