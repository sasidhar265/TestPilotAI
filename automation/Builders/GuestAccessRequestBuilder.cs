using System.Text.Json;
namespace QualityLifecycle.Automation.Builders;

public static class GuestAccessRequestBuilder
{
    public static HttpRequestMessage Entry() => new(HttpMethod.Post, Read("entry"));
    public static HttpRequestMessage Preview() => new(HttpMethod.Get, Read("preview"));
    public static HttpRequestMessage Protected(string name, string method) =>
        new(new HttpMethod(method), ReadProtected(name));

    private static JsonDocument Data() => JsonDocument.Parse(File.ReadAllText(
        Path.Combine(AppContext.BaseDirectory, "Input", "GuestAccess.Json")));

    private static string Read(string name)
    {
        using var data = Data();
        return data.RootElement.GetProperty(name).GetString()!;
    }

    private static string ReadProtected(string name)
    {
        using var data = Data();
        return data.RootElement.GetProperty("protected").GetProperty(name).GetString()!;
    }
}
