using System.Net.Http.Json;
using QualityLifecycle.Automation.Models;
namespace QualityLifecycle.Automation.Builders;
public static class RoleAccessRequestBuilder
{
    public static HttpRequestMessage Json(string method, string path, object body) => new(new HttpMethod(method), path)
    {
        Content = JsonContent.Create(body)
    };
    public static HttpRequestMessage Login(string user, string password) =>
        Json("POST", "/api/auth/login", new { username = user, password });
    public static HttpRequestMessage Account(string username, RoleAccountModel account, string role) =>
        Json("POST", "/api/admin/users", new { username, password = account.Password, role, first_name = account.FirstName, last_name = account.LastName });
    public static HttpRequestMessage Access(string username, string role) =>
        Json("PATCH", $"/api/admin/users/{username}/access", new { role, enabled = true });
}
