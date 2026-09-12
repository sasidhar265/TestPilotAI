using System.Text.Json;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;

namespace QualityLifecycle.Automation.Services;

public sealed class CodeGenerationService(ApiService api)
{
    public async Task RequestPack(string validation)
    {
        using var request = CodeGenerationRequestBuilder.Build(validation);
        await api.RequestAsync(request);
    }

    public void AssertMessage(string message)
    {
        using var document = JsonDocument.Parse(api.ResponseBody);
        Assert.That(document.RootElement.GetProperty("detail").GetString(), Does.Contain(message));
    }

    public void AssertCompletePack()
    {
        using var document = JsonDocument.Parse(api.ResponseBody);
        var root = document.RootElement;
        var files = root.GetProperty("files").EnumerateArray().ToDictionary(
            item => item.GetProperty("path").GetString()!, item => item.GetProperty("content").GetString()!);
        Assert.That(files.Keys, Does.Contain("Features/generated.feature"));
        Assert.That(files.Keys, Does.Contain("Input/TestData.Json"));
        Assert.That(files.Keys, Does.Contain("Input/CaseData.Json"));
        Assert.That(files.Keys, Does.Contain("Automation.csproj"));
        Assert.That(files["Input/TestData.Json"], Does.Contain("health"));
        Assert.That(root.GetProperty("coverage").GetArrayLength(), Is.EqualTo(4));
        Assert.That(root.GetProperty("coverage").EnumerateArray().Select(
            item => item.GetProperty("status").GetString()), Does.Not.Contain("blocked"));
        var bindings = string.Join("\n", files.Where(item => item.Key.StartsWith("StepDefinitions/")
            && item.Key.EndsWith(".cs")).Select(item => item.Value));
        Assert.That(bindings, Does.Contain("AssertStatus"));
        Assert.That(bindings, Does.Not.Contain("PendingStepException"));
    }
}
