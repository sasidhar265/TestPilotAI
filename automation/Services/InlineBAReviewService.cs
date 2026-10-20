using System.Text.Json.Nodes;
using System.IO.Compression;
using Microsoft.Extensions.DependencyInjection;
using NUnit.Framework;
using QualityLifecycle.Automation.Builders;
using QualityLifecycle.Automation.Utilities;

namespace QualityLifecycle.Automation.Services;

public sealed class InlineBAReviewService : IDisposable
{
    private readonly ServiceProvider provider = RoleAccessFixtureUtility.ClientProvider();
    private readonly HttpClient admin, other;
    private string project = "", fixture = "";
    private JsonObject run = new();
    private int status;
    private JsonObject editedRecord = new();
    public InlineBAReviewService()
    {
        var factory = provider.GetRequiredService<IHttpClientFactory>();
        admin = factory.CreateClient("role-admin"); other = factory.CreateClient("role-user");
    }
    private async Task<JsonObject> Send(HttpClient client, HttpRequestMessage request)
    {
        using (request)
        using (var response = await client.SendAsync(request))
        {
            status = (int)response.StatusCode;
            return JsonNode.Parse(await response.Content.ReadAsStringAsync())!.AsObject();
        }
    }
    private async Task Refresh()
    {
        var data = await Send(admin, new(HttpMethod.Get, $"/api/sdlc/projects/{project}/ba-reviews"));
        Assert.That(status, Is.EqualTo(200)); run = data["run"]!.DeepClone().AsObject();
    }
    public async Task Create(string name)
    {
        fixture = name;
        await Send(admin, RoleAccessRequestBuilder.Login(RoleAccessFixtureUtility.AdminUser, RoleAccessFixtureUtility.AdminPassword));
        Assert.That(status, Is.EqualTo(200));
        var record = await Send(admin, InlineBAReviewRequestBuilder.Post("projects", InlineBAReviewRequestBuilder.Data["project"]!));
        Assert.That(status, Is.EqualTo(201)); project = record["id"]!.GetValue<string>();
        await Send(admin, InlineBAReviewRequestBuilder.Source(project, fixture)); Assert.That(status, Is.EqualTo(201));
    }
    public async Task Analyse(bool force = false, int baseline = 1)
    {
        await Send(admin, InlineBAReviewRequestBuilder.Start(project, baseline, force));
        Assert.That(status, Is.EqualTo(202));
        for (var attempt = 0; attempt < 100; attempt++)
        {
            await Refresh();
            var state = run["status"]!.GetValue<string>();
            if (state is "completed" or "failed" or "cancelled") break;
            await Task.Delay(100);
        }
        Assert.That(run["status"]!.GetValue<string>(), Is.EqualTo("completed"), run.ToJsonString());
    }
    public void Finding(string type)
    {
        Assert.That(run["output"]!["schema_version"]!.GetValue<string>(), Is.EqualTo("1.0"));
        var finding = run["output"]!["findings"]![0]!;
        Assert.That(finding["finding_type"]!.GetValue<string>(), Is.EqualTo(type));
        Assert.That(finding["finding_id"]!.GetValue<string>(), Does.StartWith("FND-"));
        foreach (var reference in finding["evidence_references"]!.AsArray())
        {
            var section = run["sections"]!.AsArray().Single(item => item!["id"]!.GetValue<string>() == reference!["section_id"]!.GetValue<string>());
            Assert.That(section!["text"]!.GetValue<string>(), Does.Contain(reference!["quote"]!.GetValue<string>()));
        }
    }
    public async Task NoAutomaticApproval()
    {
        Assert.That(run["signoff"], Is.Null);
        var source = await Send(admin, new(HttpMethod.Get, $"/api/sdlc/projects/{project}"));
        var versions = source["artifacts"]!.AsArray().Where(item => item!["stage"]!.GetValue<string>() == "requirements-input").ToArray();
        Assert.That(versions.Length, Is.EqualTo(1));
        Assert.That(versions[0]!["content"]!["document"]!.GetValue<string>(), Is.EqualTo(InlineBAReviewRequestBuilder.Case(fixture)["document"]!.GetValue<string>()));
    }
    public async Task RejectAndReanalyse()
    {
        await Send(admin, InlineBAReviewRequestBuilder.Decision(project, run, "reject")); Assert.That(status, Is.EqualTo(200));
        await Analyse(true);
    }
    public async Task AssertRejection()
    {
        await Refresh();
        Assert.That(run["output"]!["findings"]![0]!["review_status"]!.GetValue<string>(), Is.EqualTo("REJECTED"));
        var history = await Send(admin, new(HttpMethod.Get, $"/api/sdlc/projects/{project}/lifecycle"));
        Assert.That(history["audit"]!.AsArray().Any(item => item!["action"]!.GetValue<string>() == "ba_review_finding_decision"), Is.True);
    }
    public async Task PendingBlocks()
    {
        await Send(admin, InlineBAReviewRequestBuilder.Signoff(project, run)); Assert.That(status, Is.EqualTo(409));
    }
    public async Task RejectAndSignoff()
    {
        var stale = run.DeepClone().AsObject();
        run = await Send(admin, InlineBAReviewRequestBuilder.Decision(project, run, "reject")); Assert.That(status, Is.EqualTo(200));
        await Send(admin, InlineBAReviewRequestBuilder.Decision(project, stale, "accept")); Assert.That(status, Is.EqualTo(409));
        run = await Send(admin, InlineBAReviewRequestBuilder.Signoff(project, run)); Assert.That(status, Is.EqualTo(200));
    }
    public async Task AssertHumanSignoff()
    {
        await Refresh();
        Assert.That(run["signoff"]!["human"]!.GetValue<bool>(), Is.True);
        Assert.That(run["signoff"]!["actor"]!.GetValue<string>(), Is.EqualTo(RoleAccessFixtureUtility.AdminUser));
        var lifecycle = await Send(admin, new(HttpMethod.Get, $"/api/sdlc/projects/{project}/lifecycle"));
        Assert.That(lifecycle["stage"]!.GetValue<string>(), Is.EqualTo("requirements_analysis"));
        Assert.That(lifecycle["audit"]!.AsArray().Any(item => item?["approval"]?.GetValue<bool>() == true), Is.False);
    }
    public async Task RevisedBaseline()
    {
        await Send(admin, InlineBAReviewRequestBuilder.Source(project, "revised-brd", 1)); Assert.That(status, Is.EqualTo(201));
        await Send(admin, InlineBAReviewRequestBuilder.Decision(project, run, "accept")); Assert.That(status, Is.EqualTo(409));
        var data = await Send(admin, new(HttpMethod.Get, $"/api/sdlc/projects/{project}/ba-reviews"));
        Assert.That(data["run"], Is.Null); Assert.That(data["impacted_runs"]!.AsArray().Count, Is.EqualTo(1));
    }
    public async Task CalculationBlocks()
    {
        run = await Send(admin, InlineBAReviewRequestBuilder.Decision(project, run, "resolve")); Assert.That(status, Is.EqualTo(200));
        await Send(admin, InlineBAReviewRequestBuilder.Signoff(project, run)); Assert.That(status, Is.EqualTo(409));
    }
    private async Task<string> Account(string role)
    {
        var name = "ba-review-bdd-" + Guid.NewGuid().ToString("N");
        var account = RoleAccessFixtureUtility.Account();
        await Send(admin, RoleAccessRequestBuilder.Account(name, account, role)); Assert.That(status, Is.EqualTo(201));
        await Send(other, RoleAccessRequestBuilder.Login(name, account.Password)); Assert.That(status, Is.EqualTo(200));
        return name;
    }
    public async Task DeveloperDenied()
    {
        var name = await Account("developer");
        await Send(admin, InlineBAReviewRequestBuilder.Post($"projects/{project}/members", new { username = name })); Assert.That(status, Is.EqualTo(201));
        await Send(other, InlineBAReviewRequestBuilder.Decision(project, run, "accept")); Assert.That(status, Is.EqualTo(403));
    }
    public async Task OutsiderDenied()
    {
        await Account("ba");
        await Send(other, new(HttpMethod.Get, $"/api/sdlc/projects/{project}/ba-reviews")); Assert.That(status, Is.EqualTo(404));
    }
    public async Task Action(string action)
    {
        run = await Send(admin, InlineBAReviewRequestBuilder.Decision(project, run, action));
        Assert.That(status, Is.EqualTo(200));
    }
    public async Task AssertAction(string expected)
    {
        await Refresh();
        Assert.That(run["output"]!["findings"]![0]!["review_status"]!.GetValue<string>(), Is.EqualTo(expected));
        var decision = run["decisions"]![0]!;
        Assert.That(decision["actor"]!.GetValue<string>(), Is.EqualTo(RoleAccessFixtureUtility.AdminUser));
        Assert.That(decision["before"], Is.Not.Null); Assert.That(decision["after"], Is.Not.Null);
        Assert.That(decision["baseline"]!.GetValue<int>(), Is.EqualTo(1));
    }
    public async Task Cancel()
    {
        var data = await Send(admin, InlineBAReviewRequestBuilder.Start(project));
        Assert.That(status, Is.EqualTo(202)); run = data["run"]!.DeepClone().AsObject();
        await Send(admin, InlineBAReviewRequestBuilder.Post($"projects/{project}/ba-reviews/{run["id"]!.GetValue<string>()}/cancel", new {}));
        Assert.That(status, Is.EqualTo(200));
    }
    public async Task AssertCancelled()
    {
        await Task.Delay(1200); await Refresh();
        Assert.That(run["status"]!.GetValue<string>(), Is.EqualTo("cancelled"));
        Assert.That(run["output"], Is.Null); Assert.That(run["signoff"], Is.Null);
    }
    private async Task<JsonArray> SupportingRecords()
    {
        using var request = InlineBAReviewRequestBuilder.SupportingRecords(project);
        using var response = await admin.SendAsync(request);
        Assert.That((int)response.StatusCode, Is.EqualTo(200));
        return JsonNode.Parse(await response.Content.ReadAsStringAsync())!.AsArray();
    }
    public async Task AssertSupportingDrafts()
    {
        var records = await SupportingRecords();
        var expected = InlineBAReviewRequestBuilder.Data["supporting_records"]!;
        Assert.That(records.Count, Is.EqualTo(run["output"]!["requirements"]!.AsArray().Count));
        foreach (var requirement in run["output"]!["requirements"]!.AsArray())
        {
            var record = records.Single(item => item!["ai_origin"]!["requirement_id"]!.GetValue<string>()
                == requirement!["requirement_id"]!.GetValue<string>())!;
            Assert.That(record["status"]!.GetValue<string>(), Is.EqualTo(expected["status"]!.GetValue<string>()));
            Assert.That(record["author"]!.GetValue<string>(), Is.EqualTo(expected["author"]!.GetValue<string>()));
            Assert.That(record["approved"]!.GetValue<bool>(), Is.False);
            Assert.That(record["ai_origin"]!["human"]!.GetValue<bool>(), Is.False);
            Assert.That(record["ai_origin"]!["review_id"]!.GetValue<string>(), Is.EqualTo(run["id"]!.GetValue<string>()));
            foreach (var reference in requirement!["source_references"]!.AsArray().Where(item => item!["source_id"]!.GetValue<string>() == "BRD"))
                Assert.That(record["references"]!.ToJsonString(), Does.Contain(reference!["section_id"]!.GetValue<string>()));
        }
        var history = await Send(admin, new(HttpMethod.Get, $"/api/sdlc/projects/{project}/lifecycle"));
        var created = history["audit"]!.AsArray().Single(item => item!["action"]!.GetValue<string>() == "ai_requirements_drafted")!;
        Assert.That(created["human"]!.GetValue<bool>(), Is.False);
        Assert.That(created["work_items"]!.AsArray().Count, Is.EqualTo(records.Count));
        Assert.That(history["evidence"]!.AsArray(), Is.Empty);
    }
    public async Task EditAndReanalyseDraft()
    {
        var records = await SupportingRecords();
        editedRecord = await Send(admin, InlineBAReviewRequestBuilder.EditSupportingRecord(project, records[0]!.AsObject()));
        Assert.That(status, Is.EqualTo(201));
        await Analyse(true);
    }
    public async Task AssertHumanDraftPreserved()
    {
        var records = await SupportingRecords();
        Assert.That(records.Count, Is.EqualTo(run["output"]!["requirements"]!.AsArray().Count));
        var record = records.Single(item => item!["id"]!.GetValue<string>() == editedRecord["id"]!.GetValue<string>())!;
        Assert.That(record["title"]!.GetValue<string>(), Is.EqualTo(InlineBAReviewRequestBuilder.Data["supporting_records"]!["edited_title"]!.GetValue<string>()));
        Assert.That(record["version"]!.GetValue<int>(), Is.EqualTo(editedRecord["version"]!.GetValue<int>()));
        Assert.That(record["approved"]!.GetValue<bool>(), Is.False);
        Assert.That(run["supporting_records"]!["created"]!.AsArray(), Is.Empty);
    }
    public async Task AnalyseNewBaseline()
    {
        await Send(admin, InlineBAReviewRequestBuilder.Source(project, fixture, 1));
        Assert.That(status, Is.EqualTo(201));
        await Analyse(baseline: 2);
    }
    public async Task AssertBaselineDrafts()
    {
        var records = await SupportingRecords();
        Assert.That(records.Count, Is.EqualTo(2 * run["output"]!["requirements"]!.AsArray().Count));
        var earlier = records.Where(item => item!["baseline"]!.GetValue<int>() == 1).ToArray();
        var current = records.Where(item => item!["baseline"]!.GetValue<int>() == 2).ToArray();
        Assert.That(earlier.All(item => item!["impacted"]!.GetValue<bool>()), Is.True);
        Assert.That(current.All(item => !item!["impacted"]!.GetValue<bool>() && !item["approved"]!.GetValue<bool>()), Is.True);
        Assert.That(run["signoff"], Is.Null);
    }
    public async Task AssertNoSupportingDrafts() => Assert.That(await SupportingRecords(), Is.Empty);
    private string baName = "";
    public async Task AddBA()
    {
        baName = await Account("ba");
        await Send(admin, InlineBAReviewRequestBuilder.Post($"projects/{project}/members", new { username = baName }));
        Assert.That(status, Is.EqualTo(201));
    }
    public async Task StoryDraftBlocked()
    {
        var records = await SupportingRecords();
        await Send(other, InlineBAReviewRequestBuilder.BacklogStory(project, records[0]!["id"]!.GetValue<string>()));
        Assert.That(status, Is.EqualTo(409));
        var state = await Send(other, new(HttpMethod.Get, $"/api/sdlc/projects/{project}/lifecycle"));
        Assert.That(state["backlog_drafting"]!["allowed"]!.GetValue<bool>(), Is.False);
    }
    public async Task StoryDraftCreated()
    {
        var records = await SupportingRecords();
        var requirement = records.Single(item => item!["kind"]!.GetValue<string>() == "requirement")!;
        var story = await Send(other, InlineBAReviewRequestBuilder.BacklogStory(project, requirement["id"]!.GetValue<string>()));
        Assert.That(status, Is.EqualTo(201));
        Assert.That(story["author"]!.GetValue<string>(), Is.EqualTo(baName));
        Assert.That(story["status"]!.GetValue<string>(), Is.EqualTo("draft"));
        Assert.That(story["link_versions"]![requirement["id"]!.GetValue<string>()]!.GetValue<int>(), Is.EqualTo(1));
        await Send(other, InlineBAReviewRequestBuilder.BacklogStory(project, requirement["id"]!.GetValue<string>(), "ready"));
        Assert.That(status, Is.EqualTo(403));
        var state = await Send(other, new(HttpMethod.Get, $"/api/sdlc/projects/{project}/lifecycle"));
        Assert.That(state["backlog_drafting"]!["allowed"]!.GetValue<bool>(), Is.True);
        Assert.That(state["stage"]!.GetValue<string>(), Is.EqualTo("requirements_analysis"));
        Assert.That(state["audit"]!.AsArray().Any(item => item?["approval"]?.GetValue<bool>() == true), Is.False);
    }
    public async Task ReviseAfterSignoff()
    {
        await Send(admin, InlineBAReviewRequestBuilder.Source(project, fixture, 1));
        Assert.That(status, Is.EqualTo(201));
    }
    public async Task DownloadBusinessDocuments()
    {
        using var request = InlineBAReviewRequestBuilder.BusinessDocument(project, "all");
        using var response = await other.SendAsync(request);
        Assert.That((int)response.StatusCode, Is.EqualTo(200));
        Assert.That(response.Content.Headers.ContentDisposition!.DispositionType, Is.EqualTo("attachment"));
        Assert.That(response.Content.Headers.ContentType!.MediaType, Is.EqualTo("application/zip"));
        Assert.That(response.Headers.CacheControl!.NoStore, Is.True);
        using var buffer = new MemoryStream(await response.Content.ReadAsByteArrayAsync());
        using var archive = new ZipArchive(buffer);
        Assert.That(archive.Entries.Select(entry => entry.FullName), Is.EquivalentTo(new[] { "business-review.md", "review-metrics.csv", "saved-brd.txt", "review-history.json" }));
        using var source = new StreamReader(archive.GetEntry("saved-brd.txt")!.Open());
        Assert.That(await source.ReadToEndAsync(), Is.EqualTo(InlineBAReviewRequestBuilder.Case(fixture)["document"]!.GetValue<string>()));
        using var metrics = new StreamReader(archive.GetEntry("review-metrics.csv")!.Open());
        Assert.That(await metrics.ReadToEndAsync(), Does.Contain("Human BA sign-off,True"));
        using var audit = new StreamReader(archive.GetEntry("review-history.json")!.Open());
        var history = JsonNode.Parse(await audit.ReadToEndAsync())!;
        Assert.That(history["baseline"]!.GetValue<int>(), Is.EqualTo(1));
        Assert.That(history["reviews"]![0]!["signoff"]!["human"]!.GetValue<bool>(), Is.True);
        foreach (var document in new[] { "business-review", "metrics", "brd", "history" })
        {
            using var download = InlineBAReviewRequestBuilder.BusinessDocument(project, document);
            using var file = await other.SendAsync(download);
            Assert.That((int)file.StatusCode, Is.EqualTo(200));
            Assert.That(file.Content.Headers.ContentDisposition!.DispositionType, Is.EqualTo("attachment"));
            Assert.That((await file.Content.ReadAsByteArrayAsync()).Length, Is.GreaterThan(0));
        }
    }
    public async Task OutsiderDocumentDenied()
    {
        await Account("ba");
        await Send(other, InlineBAReviewRequestBuilder.BusinessDocument(project, "all"));
        Assert.That(status, Is.EqualTo(404));
    }
    private JsonObject revisionReview = new(), revisedSource = new();
    public async Task PendingRevisionBlocked()
    {
        var response = await Send(admin, InlineBAReviewRequestBuilder.RevisedBRD(project, run));
        Assert.That(status, Is.EqualTo(409));
        Assert.That(response["detail"]!.GetValue<string>(), Does.Contain(
            InlineBAReviewRequestBuilder.Data["brd_revision"]!["pending_error"]!.GetValue<string>()));
        await NoAutomaticApproval();
    }
    public async Task CreateRevisedBRD()
    {
        revisionReview = run.DeepClone().AsObject();
        var response = await Send(admin, InlineBAReviewRequestBuilder.RevisedBRD(project, run));
        Assert.That(status, Is.EqualTo(202), response.ToJsonString());
        revisedSource = response["source"]!.DeepClone().AsObject();
        for (var attempt = 0; attempt < 100; attempt++)
        {
            await Refresh();
            var state = run["status"]!.GetValue<string>();
            if (state is "completed" or "failed" or "cancelled") break;
            await Task.Delay(100);
        }
        Assert.That(run["status"]!.GetValue<string>(), Is.EqualTo("completed"), run.ToJsonString());
    }
    public async Task AssertRevisedBRD(string action)
    {
        var content = revisedSource["content"]!;
        var document = content["document"]!.GetValue<string>();
        var original = InlineBAReviewRequestBuilder.Case(fixture)["document"]!.GetValue<string>();
        var strategies = new Dictionary<string, Action> {
            ["accept"] = () => Assert.That(document, Does.Contain(revisionReview["output"]!["findings"]![0]!["suggested_requirement_text"]!.GetValue<string>())),
            ["edit"] = () => Assert.That(document, Does.Contain(InlineBAReviewRequestBuilder.Data["edited_proposal"]!.GetValue<string>())),
            ["reject"] = () => Assert.That(document, Is.EqualTo(original)),
            ["clarify"] = () => Assert.That(content["ba_revision"]!["pending_feedback"]!.AsArray(), Has.Count.EqualTo(1))
        };
        strategies[action]();
        Assert.That(revisedSource["version"]!.GetValue<int>(), Is.EqualTo(2));
        Assert.That(content["source_request"]!["llm_model"]!.GetValue<string>(), Is.EqualTo("codex"));
        var snapshot = await Send(admin, new(HttpMethod.Get, $"/api/sdlc/projects/{project}"));
        var prior = snapshot["artifacts"]!.AsArray().Single(item => item!["stage"]!.GetValue<string>() == "requirements-input" && item["version"]!.GetValue<int>() == 1)!;
        Assert.That(prior["content"]!["document"]!.GetValue<string>(), Is.EqualTo(original));
        using var download = await admin.SendAsync(InlineBAReviewRequestBuilder.BusinessDocument(project, "brd"));
        Assert.That((int)download.StatusCode, Is.EqualTo(200));
        Assert.That(await download.Content.ReadAsStringAsync(), Does.Contain(document));
    }
    public async Task AssertRevalidatedBRD()
    {
        Assert.That(run["baseline"]!.GetValue<int>(), Is.EqualTo(2));
        Assert.That(run["revalidation"]!["status"]!.GetValue<string>(), Is.EqualTo("completed"));
        Assert.That(run["signoff"], Is.Null);
        var state = await Send(admin, new(HttpMethod.Get, $"/api/sdlc/projects/{project}/lifecycle"));
        Assert.That(state["approval_context"]!["assessments"]!.AsObject().Select(item => item.Key), Is.EquivalentTo(new[] { "business_analysis", "alignment" }));
        Assert.That(state["backlog_drafting"]!["signed_off"]!.GetValue<bool>(), Is.False);
    }
    public async Task StaleRevisionBlocked()
    {
        await Send(admin, InlineBAReviewRequestBuilder.RevisedBRD(project, revisionReview));
        Assert.That(status, Is.EqualTo(409));
    }
    public async Task OpenFeedbackBlocksRevisionSignoff()
    {
        var response = await Send(admin, InlineBAReviewRequestBuilder.Signoff(project, run));
        Assert.That(status, Is.EqualTo(409));
        Assert.That(response["detail"]!.GetValue<string>(), Does.Contain(
            InlineBAReviewRequestBuilder.Data["brd_revision"]!["signoff_error"]!.GetValue<string>()));
    }
    public void Dispose() { admin.Dispose(); other.Dispose(); provider.Dispose(); }
}
