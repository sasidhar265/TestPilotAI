using QualityLifecycle.Automation.Services;

namespace QualityLifecycle.Automation.TestContext;

public sealed class KnowledgeAgentScenarioContext
{
    public KnowledgeAgentService Service { get; } = new();
}
