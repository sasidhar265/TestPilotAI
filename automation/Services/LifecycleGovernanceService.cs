using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;
using QualityLifecycle.Automation.Utilities;

namespace QualityLifecycle.Automation.Services;

public sealed class LifecycleGovernanceService : IDisposable
{
    private readonly ServiceProvider provider = RoleAccessFixtureUtility.ClientProvider();
    private readonly HttpClient admin;
    private readonly HttpClient developer;
    private string project = "", username = "";
    private JsonObject state = new();
    private int status;
    public LifecycleGovernanceService()
    {
        var factory = provider.GetRequiredService<IHttpClientFactory>();
        admin = factory.CreateClient("role-admin");
        developer = factory.CreateClient("role-user");
    }
    private async Task<JsonObject> Send(HttpClient client, HttpRequestMessage request)
    {
        using (request)
        using (var response = await client.SendAsync(request))
        {
            status = (int)response.StatusCode;
            var text = await response.Content.ReadAsStringAsync();
            return JsonNode.Parse(text)?.AsObject() ?? new();
        }
    }
    private async Task Refresh()
    {
        state = await Send(admin, new(HttpMethod.Get, $"/api/sdlc/projects/{project}/lifecycle"));
        Assert.That(status, Is.EqualTo(200));
    }
    public async Task Create()
    {
        await Send(admin, RoleAccessRequestBuilder.Login(RoleAccessFixtureUtility.AdminUser, RoleAccessFixtureUtility.AdminPassword));
        Assert.That(status, Is.EqualTo(200));
        var record = await Send(admin, LifecycleRequestBuilder.Post("projects", LifecycleRequestBuilder.Fixture("SDLC.Json", "project")));
        Assert.That(status, Is.EqualTo(201));
        project = record["id"]!.GetValue<string>();
        await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/artifacts/requirements-input", LifecycleRequestBuilder.Fixture("SDLC.Json", "planning")));
        Assert.That(status, Is.EqualTo(201));
        await Refresh();
    }
    public async Task CompleteThrough(string target)
    {
        await Refresh();
        for (var attempts = 0; attempts < 30 && state["stage"]!.GetValue<string>() != target; attempts++)
        {
            var stage = state["stage"]!.GetValue<string>();
            var policy = state["definition"]!.AsArray().Single(item => item!["id"]!.GetValue<string>() == stage)!;
            foreach (var kind in policy["evidence"]!.AsArray().Select(item => item!.GetValue<string>()).ToArray())
            {
                await Send(admin, LifecycleRequestBuilder.Evidence(project, state["revision"]!.GetValue<int>(), kind));
                Assert.That(status, Is.EqualTo(201));
                await Refresh();
            }
            await Send(admin, LifecycleRequestBuilder.Decision(project, state["revision"]!.GetValue<int>(), "decision"));
            Assert.That(status, Is.EqualTo(201));
            await Refresh();
        }
        Assert.That(state["stage"]!.GetValue<string>(), Is.EqualTo(target));
    }
    public async Task AdvanceWithoutEvidence() => await Send(admin,
        LifecycleRequestBuilder.Decision(project, state["revision"]!.GetValue<int>(), "decision"));
    public async Task Stale() => await Send(admin, LifecycleRequestBuilder.Decision(project, 0, "decision"));
    public async Task Reject() => await Send(admin,
        LifecycleRequestBuilder.Decision(project, state["revision"]!.GetValue<int>(), "rejection"));
    public async Task ChangeSource() => await Send(admin,
        LifecycleRequestBuilder.Post($"projects/{project}/artifacts/requirements-input", LifecycleRequestBuilder.Fixture("SDLC.Json", "planning-revision")));
    public void AssertStatus(int expected) => Assert.That(status, Is.EqualTo(expected));
    public async Task AssertStage(string expected)
    {
        await Refresh();
        Assert.That(state["stage"]!.GetValue<string>(), Is.EqualTo(expected));
    }
    public void AssertApprovals()
    {
        var approvals = state["audit"]!.AsArray().Where(item => item?["approval"]?.GetValue<bool>() == true).ToArray();
        Assert.That(approvals.Length, Is.EqualTo(4));
        foreach (var approval in approvals)
        {
            Assert.That(approval!["actor"]!.GetValue<string>(), Is.EqualTo(RoleAccessFixtureUtility.AdminUser));
            Assert.That(approval["artifact_version"]!.GetValue<int>(), Is.EqualTo(1));
            Assert.That(approval["human"]!.GetValue<bool>(), Is.True);
            Assert.That(approval["created_at"]!.GetValue<string>(), Is.Not.Empty);
        }
    }
    public void AssertImpact() => Assert.That(state["impacted_evidence"]!.AsArray().Count, Is.GreaterThan(0));
    public async Task DeveloperAttempts()
    {
        username = "lifecycle-bdd-" + Guid.NewGuid().ToString("N");
        var account = RoleAccessFixtureUtility.Account();
        await Send(admin, RoleAccessRequestBuilder.Account(username, account, "developer"));
        Assert.That(status, Is.EqualTo(201));
        await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/members", new
        {
            username
        }));
        Assert.That(status, Is.EqualTo(201));
        await Send(developer, RoleAccessRequestBuilder.Login(username, account.Password));
        Assert.That(status, Is.EqualTo(200));
        await Send(developer, LifecycleRequestBuilder.Decision(project, state["revision"]!.GetValue<int>(), "decision"));
    }
    public async Task LinkedRecordsAndImpact()
    {
        var requirement = await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", LifecycleRequestBuilder.Fixture("Lifecycle.Json", "requirement")));
        Assert.That(status, Is.EqualTo(201));
        var storyBody = LifecycleRequestBuilder.Fixture("Lifecycle.Json", "story");
        storyBody["links"] = new JsonArray(requirement["id"]!.GetValue<string>());
        var story = await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", storyBody));
        Assert.That(status, Is.EqualTo(201));
        var testBody = LifecycleRequestBuilder.Fixture("Lifecycle.Json", "test_case");
        testBody["links"] = new JsonArray(story["id"]!.GetValue<string>());
        await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", testBody));
        Assert.That(status, Is.EqualTo(201));
        requirement["base_version"] = 1;
        requirement["title"] = "BDD synthetic revised requirement";
        await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", requirement));
        Assert.That(status, Is.EqualTo(201));
        using var response = await admin.GetAsync($"/api/sdlc/projects/{project}/work-items");
        Assert.That((int)response.StatusCode, Is.EqualTo(200));
        var records = JsonNode.Parse(await response.Content.ReadAsStringAsync())!.AsArray();
        Assert.That(records.Where(item => item!["kind"]!.GetValue<string>() != "requirement")
            .All(item => item!["impacted"]!.GetValue<bool>()), Is.True);
        Assert.That(records.Single(item => item!["id"]!.GetValue<string>() == story["id"]!.GetValue<string>())!["link_versions"]![requirement["id"]!.GetValue<string>()]!.GetValue<int>(), Is.EqualTo(1));
    }
    private async Task<JsonObject> InlineRequirement()
    {
        var record = await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", LifecycleRequestBuilder.Fixture("Lifecycle.Json", "requirement")));
        Assert.That(status, Is.EqualTo(201));
        return record;
    }
    public async Task InlineApproval()
    {
        var record = await InlineRequirement();
        var id = record["id"]!.GetValue<string>();
        await Send(admin, LifecycleRequestBuilder.Annotation(project, id, "inline-comment"));
        Assert.That(status, Is.EqualTo(201));
        record["base_version"] = 1;
        record["description"] = "BDD clarified requirement after inline review";
        await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", record));
        Assert.That(status, Is.EqualTo(201));
        var detail = await Send(admin, LifecycleRequestBuilder.Detail(project, id));
        Assert.That(status, Is.EqualTo(200));
        Assert.That(detail["versions"]!.AsArray().Count, Is.EqualTo(2));
        Assert.That(detail["annotations"]![0]!["base_version"]!.GetValue<int>(), Is.EqualTo(1));
        Assert.That(detail["annotations"]![0]!["actor"]!.GetValue<string>(), Is.EqualTo(RoleAccessFixtureUtility.AdminUser));
        await CompleteThrough("backlog_generation");
        var approval = state["audit"]!.AsArray().Single(row => row?["stage"]?.GetValue<string>() == "stakeholder_approval");
        Assert.That(approval!["work_item_versions"]![id]!.GetValue<int>(), Is.EqualTo(2));
        Assert.That(approval["human"]!.GetValue<bool>(), Is.True);
        await AssertQueue();
    }
    public async Task InlineStale()
    {
        var record = await InlineRequirement();
        var id = record["id"]!.GetValue<string>();
        record["base_version"] = 1;
        await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", record));
        Assert.That(status, Is.EqualTo(201));
        await Send(admin, LifecycleRequestBuilder.Annotation(project, id, "inline-comment"));
        Assert.That(status, Is.EqualTo(409));
        var detail = await Send(admin, LifecycleRequestBuilder.Detail(project, id));
        Assert.That(detail["annotations"]!.AsArray(), Is.Empty);
        Assert.That(detail["versions"]!.AsArray().Count, Is.EqualTo(2));
    }
    public async Task InlineDeveloper()
    {
        var record = await InlineRequirement();
        var id = record["id"]!.GetValue<string>();
        await DeveloperAttempts();
        Assert.That(status, Is.EqualTo(403));
        var detail = await Send(developer, LifecycleRequestBuilder.Detail(project, id));
        Assert.That(status, Is.EqualTo(200));
        Assert.That(detail["editable_fields"]!.AsArray(), Is.Empty);
        await Send(developer, LifecycleRequestBuilder.Annotation(project, id, "inline-comment"));
        Assert.That(status, Is.EqualTo(201));
        await Send(developer, LifecycleRequestBuilder.Annotation(project, id, "inline-suggestion"));
        Assert.That(status, Is.EqualTo(403));
        record["base_version"] = 1;
        await Send(developer, LifecycleRequestBuilder.Post($"projects/{project}/work-items", record));
        Assert.That(status, Is.EqualTo(403));
    }
    public async Task InlineUnknownSuggestion()
    {
        var record = await InlineRequirement();
        var id = record["id"]!.GetValue<string>();
        await Send(admin, LifecycleRequestBuilder.Annotation(project, id, "inline-suggestion"));
        Assert.That(status, Is.EqualTo(409));
        var detail = await Send(admin, LifecycleRequestBuilder.Detail(project, id));
        Assert.That(detail["annotations"]!.AsArray(), Is.Empty);
        Assert.That(detail["item"]!["version"]!.GetValue<int>(), Is.EqualTo(1));
        Assert.That(detail["suggestions"]!.AsArray(), Is.Empty);
    }
    public async Task AssertCatalogueAndHealth()
    {
        using var catalogueResponse = await admin.GetAsync("/api/agents");
        Assert.That((int)catalogueResponse.StatusCode, Is.EqualTo(200));
        var agents = JsonNode.Parse(await catalogueResponse.Content.ReadAsStringAsync())!.AsArray();
        var ids = agents.Select(agent => agent!["id"]!.GetValue<string>()).ToArray();
        Assert.That(ids.Length, Is.EqualTo(29));
        Assert.That(ids.Distinct().Count(), Is.EqualTo(ids.Length));
        Assert.That(ids.Take(7), Is.EqualTo(new[] { "sdlc-planning", "sdlc-requirements", "sdlc-design", "sdlc-development", "sdlc-testing", "sdlc-release", "sdlc-operations" }));
        Assert.That(ids, Does.Contain("business-analyst"));
        Assert.That(ids, Does.Contain("execution-agent"));
        Assert.That(ids, Does.Contain("automation-execution-agent"));
        using var healthResponse = await admin.GetAsync("/api/health");
        Assert.That((int)healthResponse.StatusCode, Is.EqualTo(200));
        var health = JsonNode.Parse(await healthResponse.Content.ReadAsStringAsync())!.AsObject();
        Assert.That(health["codex_model"]!.GetValue<string>(), Is.EqualTo("gpt-6-astra"));
        Assert.That(health["copilot_model"]!.GetValue<string>(), Is.EqualTo("claude-haiku-4.5"));
    }
    public async Task AssertQueue()
    {
        using var response = await admin.GetAsync("/api/sdlc/queue");
        Assert.That((int)response.StatusCode, Is.EqualTo(200));
        var rows = JsonNode.Parse(await response.Content.ReadAsStringAsync())!.AsArray();
        var queue = rows.Single(row => row!["project"]!["id"]!.GetValue<string>() == project)!["lifecycle"]!;
        Assert.That(queue["stage"]!.GetValue<string>(), Is.EqualTo(state["stage"]!.GetValue<string>()));
        Assert.That(queue["baseline"]!.GetValue<int>(), Is.EqualTo(state["baseline"]!.GetValue<int>()));
        using var recordsResponse = await admin.GetAsync($"/api/sdlc/projects/{project}/work-items");
        Assert.That((int)recordsResponse.StatusCode, Is.EqualTo(200));
        var records = JsonNode.Parse(await recordsResponse.Content.ReadAsStringAsync())!.AsArray();
        var metrics = rows.Single(row => row!["project"]!["id"]!.GetValue<string>() == project)!["metrics"]!;
        Assert.That(metrics["requirements"]!.GetValue<int>(), Is.EqualTo(records.Count(row => row!["kind"]!.GetValue<string>() == "requirement")));
        Assert.That(metrics["approved_requirements"]!.GetValue<int>(), Is.EqualTo(records.Count(row => row!["approved"]!.GetValue<bool>())));
    }
    public async Task AssertStoryReadinessGate()
    {
        var requirement = await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", LifecycleRequestBuilder.Fixture("Lifecycle.Json", "requirement")));
        Assert.That(status, Is.EqualTo(201));
        var body = LifecycleRequestBuilder.Fixture("Lifecycle.Json", "story");
        body["links"] = new JsonArray(requirement["id"]!.GetValue<string>());
        var story = await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", body));
        Assert.That(status, Is.EqualTo(201));
        story["base_version"] = 1;
        story["status"] = "ready";
        await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", story));
        Assert.That(status, Is.EqualTo(409));
        await CompleteThrough("prioritisation_estimation");
        await Send(admin, LifecycleRequestBuilder.Post($"projects/{project}/work-items", story));
        Assert.That(status, Is.EqualTo(201));
    }
    public async Task AssertSequence()
    {
        await Refresh();
        var phases = state["phases"]!.AsArray();
        var expected = LifecycleRequestBuilder.Fixture("Lifecycle.Json", "sequence")["phase_ids"]!.AsArray().Select(item => item!.GetValue<string>());
        Assert.That(phases.Select(item => item!["id"]!.GetValue<string>()), Is.EqualTo(expected));
        var stages = phases.SelectMany(phase => phase!["stages"]!.AsArray().Select(item => item!.GetValue<string>())).ToArray();
        Assert.That(stages.Distinct().Count(), Is.EqualTo(stages.Length));
        Assert.That(stages, Is.EquivalentTo(state["definition"]!.AsArray().Select(item => item!["id"]!.GetValue<string>())));
        Assert.That(state["phase"]!.GetValue<string>(), Is.EqualTo("requirements"));
        await CompleteThrough("stakeholder_approval");
        Assert.That(state["phase"]!.GetValue<string>(), Is.EqualTo("business-approval"));
        await Reject();
        AssertStatus(201);
        await Refresh();
        Assert.That(state["phase"]!.GetValue<string>(), Is.EqualTo("requirements"));
        Assert.That(state["stage"]!.GetValue<string>(), Is.EqualTo("clarification"));
    }
    public async Task Cleanup()
    {
        if (username.Length > 0)
            await Send(admin, new(HttpMethod.Delete, $"/api/admin/users/{username}"));
    }
    public void Dispose()
    {
        admin.Dispose();
        developer.Dispose();
        provider.Dispose();
    }
}
