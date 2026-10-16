using System.Text.Json;
using QualityLifecycle.Automation.Utilities;

namespace QualityLifecycle.Automation.Builders;

public static class WorkspacePresentationRequestBuilder
{
    public static (HttpRequestMessage Request, bool NoStore) Page(string fixture)
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "WorkspacePresentation.Json")));
        var input = data.RootElement.GetProperty(fixture);
        var request = new HttpRequestMessage(HttpMethod.Get, input.GetProperty("path").GetString());
        AuthenticationUtility.Apply(request);
        return (request, input.GetProperty("noStore").GetBoolean());
    }
}
