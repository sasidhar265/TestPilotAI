using System.Text.Json;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;
using QualityLifecycle.Automation.Models;
using QualityLifecycle.Automation.Utilities;
namespace QualityLifecycle.Automation.Services;
public sealed class RoleAccessService : IDisposable
{
    private readonly HttpClient admin;
    private readonly HttpClient user;
    public RoleAccessService(IHttpClientFactory factory)
    {
        admin = factory.CreateClient("role-admin");
        user = factory.CreateClient("role-user");
    }
    private RoleAccessFixtureModel fixture = null!;
    private string username = "";
    private readonly RoleAccountModel account = RoleAccessFixtureUtility.Account();
    private string profile = "";
    private int permittedStatus, restrictedStatus, sessionStatus, homeStatus;
    private string homeLocation = "/";
    private static async Task<int> Send(HttpClient client, HttpRequestMessage request)
    {
        using (request)
        using (var response = await client.SendAsync(request))
            return (int)response.StatusCode;
    }
    public async Task CreateAccount(string name)
    {
        fixture = RoleAccessFixtureUtility.Read(name);
        Assert.That(await Send(admin, RoleAccessRequestBuilder.Login(
            RoleAccessFixtureUtility.AdminUser, RoleAccessFixtureUtility.AdminPassword)), Is.EqualTo(200));
        username = "role-bdd-" + Guid.NewGuid().ToString("N");
        Assert.That(await Send(admin, RoleAccessRequestBuilder.Account(username, account, fixture.Role)), Is.EqualTo(201));
        Assert.That(await Send(user, RoleAccessRequestBuilder.Login(username, account.Password)), Is.EqualTo(200));
    }
    public async Task Exercise()
    {
        using var response = await user.GetAsync("/api/auth/profile");
        Assert.That((int)response.StatusCode, Is.EqualTo(200));
        profile = await response.Content.ReadAsStringAsync();
        using var home = await user.GetAsync("/");
        homeStatus = (int)home.StatusCode;
        homeLocation = home.Headers.Location?.OriginalString ?? "/";
        permittedStatus = await Send(user, RoleAccessRequestBuilder.Json(fixture.AllowedMethod, fixture.AllowedPath, fixture.AllowedBody));
        restrictedStatus = await Send(user, RoleAccessRequestBuilder.Json(fixture.DeniedMethod, fixture.DeniedPath, fixture.DeniedBody));
    }
    public void AssertCapabilities()
    {
        using var document = JsonDocument.Parse(profile);
        Assert.That(document.RootElement.GetProperty("role").GetString(), Is.EqualTo(fixture.Role));
        Assert.That(document.RootElement.GetProperty("capabilities").GetProperty("generation_targets")
            .EnumerateArray().Select(item => item.GetString()), Is.EqualTo(fixture.Targets));
        Assert.That(document.RootElement.GetProperty("capabilities").GetProperty("home_path").GetString(), Is.EqualTo(fixture.HomePath));
        Assert.That(homeLocation, Is.EqualTo(fixture.HomePath));
        Assert.That(homeStatus, Is.EqualTo(fixture.HomePath == "/" ? 200 : 303));
        Assert.That(permittedStatus, Is.EqualTo(fixture.AllowedStatus));
        Assert.That(restrictedStatus, Is.EqualTo(fixture.DeniedStatus));
    }
    public async Task ChangeRole()
    {
        Assert.That(await Send(admin, RoleAccessRequestBuilder.Access(username, fixture.ChangedRole)), Is.EqualTo(200));
        sessionStatus = await Send(user, new HttpRequestMessage(HttpMethod.Get, "/api/auth/profile"));
    }
    public void AssertRevoked() => Assert.That(sessionStatus, Is.EqualTo(401));
    public async Task Cleanup()
    {
        if (username.Length > 0)
            Assert.That(await Send(admin, new HttpRequestMessage(HttpMethod.Delete, $"/api/admin/users/{username}")), Is.EqualTo(200));
    }
    public void Dispose() { admin.Dispose(); user.Dispose(); }
}
