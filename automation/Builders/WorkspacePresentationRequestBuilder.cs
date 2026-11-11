using System.Text.Json;
using QualityLifecycle.Automation.Models;

namespace QualityLifecycle.Automation.Builders;

public static class WorkspacePresentationRequestBuilder
{
    public static WorkspacePresentationModel Page(string name)
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "WorkspacePresentation.Json")));
        return data.RootElement.GetProperty("pages").GetProperty(name)
            .Deserialize<WorkspacePresentationModel>(new JsonSerializerOptions(JsonSerializerDefaults.Web))
            ?? throw new InvalidOperationException("Page contract fixture is missing.");
    }

    public static string[] CatalogIds()
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "WorkspacePresentation.Json")));
        return data.RootElement.GetProperty("catalog_ids").EnumerateArray()
            .Select(item => item.GetString()!).ToArray();
    }
}
