using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace QualityLifecycle.Automation.Models;

public sealed record DomainProfileModel(
    string Id, string Name, string Description, string Instructions, JsonObject Baseline,
    [property: JsonPropertyName("expected_revision")] int ExpectedRevision,
    [property: JsonPropertyName("review_note")] string ReviewNote, bool Confirmed);
