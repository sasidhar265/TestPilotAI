using System.Text.Json;
namespace QualityLifecycle.Automation.Models;

public sealed record FinanceFixtureModel(JsonElement Request, JsonElement Expected, int Status, bool? Matches);
