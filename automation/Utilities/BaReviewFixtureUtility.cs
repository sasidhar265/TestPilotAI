using System.Text.Json;
using QualityLifecycle.Automation.Models;
namespace QualityLifecycle.Automation.Utilities;
public static class BaReviewFixtureUtility
{
    public static BaReviewFixtureModel Read(string name)
    {
        using var data = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Input", "BaReview.Json")));
        var item = data.RootElement.GetProperty(name);
        return new(item.GetProperty("request").Clone(), item.GetProperty("status").GetInt32());
    }
}
