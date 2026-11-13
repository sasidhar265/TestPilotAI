using System.Text.Json;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;
namespace QualityLifecycle.Automation.Services;
public sealed class PromptIntentService(ApiService api)
{
    public async Task Interpret(string fixture)
    {
        using var request = PromptIntentRequestBuilder.Build(fixture);
        await api.RequestAsync(request);
    }
    public void AssertWorkflow(string workflow)
    {
        using var result = JsonDocument.Parse(api.ResponseBody);
        Assert.That(result.RootElement.GetProperty("workflow").GetString(), Is.EqualTo(workflow));
        Assert.That(result.RootElement.GetProperty("summary").GetString(), Is.Not.Empty);
    }
    public void AssertQuestions()
    {
        using var result = JsonDocument.Parse(api.ResponseBody);
        Assert.That(result.RootElement.GetProperty("questions").GetArrayLength(), Is.Positive);
    }
}
