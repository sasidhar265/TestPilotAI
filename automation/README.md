# Quality Lifecycle Studio C# BDD automation

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

`QUALITY_LIFECYCLE_BASE_URL` defaults to `http://127.0.0.1:8000`. Security scenarios require
`API_AUTH_TOKEN` to be configured and only assert behavior; they never print its value.

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
the organizational-memory directory. The lightweight application Docker image does not bundle this
local execution toolchain.

Pass/fail/not-run counts represent test scenarios (outline example rows are separate tests).
Not run uses TRX `NotExecuted` outcomes, not skipped individual steps after a scenario failure.
Authentication prerequisites and assertions remain those defined by the existing repository tests.
