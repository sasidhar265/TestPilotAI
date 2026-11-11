using System.Text.Json;
using System.Text.Json.Nodes;
using QualityLifecycle.Automation.Models;

namespace QualityLifecycle.Automation.Builders;

public static class DomainProfileRequestBuilder
{
    public static JsonObject Definition()
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "DomainProfiles.Json")));
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        var model = data.RootElement.GetProperty("profile").Deserialize<DomainProfileModel>(options)
            ?? throw new InvalidOperationException("Domain profile fixture could not be read.");
        return JsonSerializer.SerializeToNode(model with { Id = model.Id + "-" + Guid.NewGuid().ToString("N") }, options)!.AsObject();
    }
}
