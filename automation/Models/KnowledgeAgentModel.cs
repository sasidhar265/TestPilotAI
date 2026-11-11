using System.Text.Json.Serialization;

namespace QualityLifecycle.Automation.Models;

public sealed record KnowledgeAgentModel(
    string Name,
    string Purpose,
    string Domain,
    string Profile,
    string[] Stages,
    [property: JsonPropertyName("source_reference")] string SourceReference,
    string Instructions,
    string Knowledge);
