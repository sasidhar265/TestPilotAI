using System.Net.Http.Headers;

namespace QualityLifecycle.Automation.Utilities;

public static class AuthenticationUtility
{
    public static bool IsConfigured =>
        !string.IsNullOrWhiteSpace(ConfigurationUtility.GetValue("API_AUTH_TOKEN"))
        || !string.IsNullOrWhiteSpace(ConfigurationUtility.GetValue("API_SESSION_COOKIE"));

    public static void Apply(HttpRequestMessage request)
    {
        var token = ConfigurationUtility.GetValue("API_AUTH_TOKEN");
        var cookie = ConfigurationUtility.GetValue("API_SESSION_COOKIE");
        if (!string.IsNullOrWhiteSpace(token))
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        else if (!string.IsNullOrWhiteSpace(cookie))
            request.Headers.Add("Cookie", cookie);
    }
}
