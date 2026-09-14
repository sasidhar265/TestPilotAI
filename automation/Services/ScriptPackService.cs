using System.IO.Compression;
using System.Text.Json;
using System.Xml.Linq;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;

namespace QualityLifecycle.Automation.Services;

public sealed class ScriptPackService(ApiService api)
{
    private string fixture = string.Empty;

    public async Task Send(string name, string action)
    {
        fixture = name;
        using var request = ScriptPackRequestBuilder.Build(name, action);
        await api.RequestAsync(request);
    }

    public void AssertFile(string path, string content)
    {
        using var result = JsonDocument.Parse(api.ResponseBody);
        var files = result.RootElement.GetProperty("files").EnumerateArray().ToArray();
        var file = files.Single(item => item.GetProperty("path").GetString() == path);
        Assert.That(file.GetProperty("content").GetString(), Does.Contain(content));
        if (path.EndsWith(".jmx", StringComparison.Ordinal))
        {
            var xml = XDocument.Parse(file.GetProperty("content").GetString()!);
            Assert.That(xml.Descendants("HTTPSamplerProxy").Count(), Is.EqualTo(1));
            Assert.That(xml.Descendants("ResponseAssertion").Count(), Is.EqualTo(1));
        }
    }

    public void AssertMappings()
    {
        using var result = JsonDocument.Parse(api.ResponseBody);
        var expected = ScriptPackRequestBuilder.Input(fixture).GetProperty("suite").GetProperty("test_cases")
            .EnumerateArray().Select(item => item.GetProperty("id").GetString()).ToArray();
        var actual = result.RootElement.GetProperty("case_ids").EnumerateArray()
            .Select(item => item.GetString()).ToArray();
        Assert.That(actual, Is.EquivalentTo(expected));
        var paths = result.RootElement.GetProperty("files").EnumerateArray()
            .Select(item => item.GetProperty("path").GetString()).ToArray();
        Assert.That(paths, Does.Contain("Input/TestData.Json"));
        Assert.That(paths, Does.Contain("Input/CaseData.Json"));
    }

    public async Task AssertArchive(string path)
    {
        var bytes = await api.Response!.Content.ReadAsByteArrayAsync();
        using var archive = new ZipArchive(new MemoryStream(bytes), ZipArchiveMode.Read);
        Assert.That(archive.GetEntry(path), Is.Not.Null);
        Assert.That(archive.GetEntry("README.md"), Is.Not.Null);
        Assert.That(archive.GetEntry("Input/TestData.Json"), Is.Not.Null);
        Assert.That(archive.Entries.All(entry => !entry.FullName.Contains("..")), Is.True);
    }
}
