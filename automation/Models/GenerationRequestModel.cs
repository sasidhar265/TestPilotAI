using System.Text.Json.Serialization;
namespace QualityLifecycle.Automation.Models;

public sealed record GenerationRequestModel([property: JsonPropertyName("description")] string Description);
