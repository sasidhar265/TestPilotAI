# Quality Lifecycle Studio C# BDD automation

`Features/JiraStories.feature` verifies story publication rejects missing approval,
unknown or duplicate selections, and blank reviewers before contacting Jira. It uses
the shared Workflow HttpClient service, request builder, bindings and Input/Workflow.Json.
Run it with `--filter FullyQualifiedName~JiraStoryApprovalBoundary` against a local test app.
These rejection scenarios never create Jira issues. Jira creation payloads and partial
failures are covered with mocked HTTP responses in `tests/test_jira_stories.py`; actual
Jira creation requires a configured test project and has not been verified by these tests.

Native JMeter/SQL/Oracle script-pack API coverage is in `Features/ScriptPacks.feature`, with
its bindings, HttpClient service, request builder and `Input/ScriptPacks.Json` fixtures.
See [test script packs](../docs/test-script-packs.md) for generation and execution instructions.

This project contains live ReqnRoll scenarios for the UI, API, and security boundaries.
The scenarios intentionally run against a separately started application so CI can choose
the environment and credentials without embedding secrets in source control.

Start the app, then run the API and security scenarios:

```bash
QUALITY_LIFECYCLE_BASE_URL=http://127.0.0.1:8000 \
API_AUTH_TOKEN="$API_AUTH_TOKEN" \
dotnet test automation/QualityLifecycle.Automation.csproj --filter "TestCategory=api|TestCategory=security"
```

Install the Playwright browser once before UI runs:

```bash
pwsh automation/bin/Debug/net8.0/playwright.ps1 install chromium
dotnet test automation/QualityLifecycle.Automation.csproj --filter TestCategory=ui
```

`QUALITY_LIFECYCLE_BASE_URL` defaults to `http://127.0.0.1:8000`. Security scenarios require authenticated access to be configured. The in-app runner uses
`API_AUTH_TOKEN` when available; otherwise it authenticates the configured
`APP_USERNAME`/`APP_PASSWORD` and supplies a signed `API_SESSION_COOKIE` to the BDD process.
Request builders attach credentials only to authenticated requests. The negative security
scenario sends neither a bearer token nor a session cookie, and still requires HTTP 401.
Session cookies and passwords are redacted from runner output and API attachments.

The Python unit and integration suite remains under `tests/` and runs with `pytest`. The
ReqnRoll project here is the live UI/API/security automation suite and runs with `dotnet test`.

## Allure HTML reports from the workspace

The project includes the native [Allure Reqnroll adapter](https://allurereport.org/docs/reqnroll/).
Install Java and Allure **2** CLI with `--single-file` support on the application host, then run:

```bash
dotnet restore automation/QualityLifecycle.Automation.csproj
```

Open **Progress & execution → Run BDD tests**. The runner executes only this project and collects
TRX counts plus native Allure scenario/step results in a fresh temporary directory per run. It then
runs `allure generate --single-file` and persists the standalone HTML for downloading. No generated
suite or unit-test project is executed. Report generation errors are displayed separately from test
failures, so a missing Allure CLI never changes a pass/fail result.

`ALLURE_EXECUTABLE` defaults to `allure`; `ALLURE_TIMEOUT_SECONDS` defaults to 120. The runner sets
`ALLURE_CONFIG` for each execution, so concurrent result files and older results are never mixed.
The runtime needs .NET 8, restored packages, Playwright Chromium, Java, Allure 2, and write access to
the organizational-memory directory. The application Docker image bundles this toolchain and builds the project during deployment.
Render runs target `http://127.0.0.1:10000`; `ALLOWED_HOSTS` must include `127.0.0.1`
and `localhost` as well as the public hostname. Existing Render services must apply the
updated environment values from `render.yaml` and redeploy the image. Local build
outputs are excluded from the Docker context to keep restored paths platform-correct.
The validation API scenario supplies the configured bearer token; the security scenario
intentionally omits it.

Pass/fail/not-run counts represent test scenarios (outline example rows are separate tests).
Not run uses TRX `NotExecuted` outcomes, not skipped individual steps after a scenario failure.
Authentication prerequisites and assertions remain those defined by the existing repository tests.

## Framework folders

The project now uses `Reqnroll`, `Features`, `StepDefinitions`, `Hooks`, `TestContext`,
`Services`, `Builders`, `Models`, `Utilities`, `TestResults/Reports`, and `Input` as sibling
folders. `Reqnroll/Repository.runsettings` configures TRX output. The project remains at
`automation/QualityLifecycle.Automation.csproj`, so existing build and CI entry points work.

`WorkspaceStepDefinition.cs` delegates transport/browser work to services and request
construction to the builder/model. `Hooks/Hooks.cs` disposes scenario resources.
`Input/TestData.Json` is copied to build output and read by the security scenario.

Run with:

```bash
dotnet test automation/QualityLifecycle.Automation.csproj --results-directory automation/TestResults/Reports
```

Live workspace Allure HTML reports now also go into
`automation/TestResults/Reports`; old report links still resolve to the earlier storage location.
Persist this directory on deployed hosts to retain new reports across redeployments.

## Approved quotation payload builder

C# API handling uses `System.Net.Http.HttpClient` in `Services/ApiService.cs`.
Generated C# packs also use an injected HttpClient with `IHttpClientFactory`/`AddHttpClient`,
asynchronous sends, and cancellation support. Generation validation rejects alternative
HTTP clients such as RestSharp, Flurl, legacy WebRequest, and Playwright API request contexts.

`Input/QuotationRequest.Json` contains the exact user-supplied Outlet/Finance/Vehicle/Parameters
payload. `Models/QuotationRequestModel.cs` preserves every JSON name, including `Outlet.code`
and `Vehicle.VehicleRegstrationDate`. `Builders/QuotationRequestbuilder.cs` exposes typed fluent
setters for those existing fields; decimal fields remain decimal and the date remains a string.

```csharp
var request = QuotationRequestBuilder
    .FromFile("Input/QuotationRequest.Json")
    .WithDeposit(5000m)
    .WithTerm(36)
    .Build();
```

`QuotationRequestService` accepts `ApprovedQuotationRequestStrategy` for the unchanged payload
or `ConfiguredQuotationRequestStrategy` with an action applying explicit typed builder overrides.
Each build is an independent immutable snapshot. Unknown JSON fields and missing required members
are rejected; the builder does not invent fields or validate unprovided business rules.
The application workspace's own `/api/generate` request model remains separate from this finance
endpoint payload.

Generated packs receive the same model, builder, strategies and Input file. For quotation features,
named request fixtures also go through the typed builder. The deterministic step
`Given the approved quotation request` loads the exact default payload. Configure the actual
method, endpoint and credentials separately; no finance endpoint or success result is inferred.

Across all generated languages, StepDefinitions must delegate to services/strategies, with no
if/else, switch/match/case, unless or ternary expressions. Static checks enforce this policy;
ordinary validation guards remain allowed inside services.

## Code-generation approval regressions

`Features/CodeGeneration.feature` checks failed and inconsistent Quality Gate reports and full-pack
creation with a current passing report despite historical suite notes. The scenarios use
`Input/CodeGeneration.Json`, the dedicated request builder and `CodeGenerationService` through the
shared HttpClient service. The input describes the existing workspace health endpoint; it does
not introduce a finance request contract. These checks do not call AI providers.

Run against a separately started application with:

```bash
dotnet test automation/QualityLifecycle.Automation.csproj --filter FullyQualifiedName~CodeGeneration
```

This verifies the code-generation API boundary. Execute the returned pack separately to verify
its discovered Gherkin scenarios against `API_BASE_URL`; repository API results are not generated
suite execution evidence.

## Running installed packs on Render

The Docker deployment builds the repository project once. `AUTOMATION_SKIP_BUILD=true`
uses those binaries until a generated C# pack is installed. Installation marks the project
as requiring a build; the next BDD run restores dependencies and builds the current sources
before executing them. The marker remains after build or startup failures so retries cannot
silently fall back to the previous assembly. Existing feature files are retained.

If a Render run fails, open its saved runner output in Progress & execution. A build/restore
failure, failed scenario, and Allure report failure are separate outcomes. Check that
`QUALITY_LIFECYCLE_BASE_URL` points to `http://127.0.0.1:10000` and that the deployed Docker
image contains the .NET SDK, browser dependencies, and Allure. Changes to the Docker image
or application source require a deployment before they affect the hosted runner.

## Microsoft User Secrets in local development

The project uses `UserSecretsId=quality-lifecycle-studio-local`. Set
`USER_SECRETS_ENABLED=true` and `ENVIRONMENT=development` to load credentials from
Microsoft's local `secrets.json` during direct `dotnet test` runs. The Python app can
read the same store. See [local User Secrets setup](../docs/local-user-secrets.md) for
commands, file locations, and precedence. Production uses environment variables.
