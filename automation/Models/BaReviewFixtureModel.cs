using System.Text.Json;
namespace QualityLifecycle.Automation.Models;
public sealed record BaReviewFixtureModel(JsonElement Request, int Status);
