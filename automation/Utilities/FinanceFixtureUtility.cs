using System.Text.Json;
using QualityLifecycle.Automation.Models;
namespace QualityLifecycle.Automation.Utilities;

public static class FinanceFixtureUtility
{
    public static FinanceFixtureModel Read(string name)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(
            AppContext.BaseDirectory, "Input", "FinanceCalculations.Json")));
        var data = document.RootElement.GetProperty(name);
        return new FinanceFixtureModel(data.GetProperty("request").Clone(),
            data.TryGetProperty("expected", out var expected) ? expected.Clone() : default,
            data.GetProperty("status").GetInt32(),
            data.TryGetProperty("matches", out var matches) ? matches.GetBoolean() : null);
    }
}
