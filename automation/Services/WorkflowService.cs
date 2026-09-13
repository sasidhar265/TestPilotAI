using NUnit.Framework;
using QualityLifecycle.Automation.Builders;

namespace QualityLifecycle.Automation.Services;

public sealed class WorkflowService(ApiService api)
{
    public async Task ValidateHandoff(string fixture)
    {
        using var request = WorkflowRequestBuilder.Build(fixture);
        await api.RequestAsync(request);
    }

    public void AssertResponse(string text) => Assert.That(api.ResponseBody, Does.Contain(text));
}
