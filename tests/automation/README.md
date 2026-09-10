# Quality Lifecycle Studio C# BDD automation

This project contains live ReqnRoll scenarios for the UI, API, and security boundaries.
The scenarios intentionally run against a separately started application so CI can choose
the environment and credentials without embedding secrets in source control.

Start the app, then run the API and security scenarios:

```bash
QUALITY_LIFECYCLE_BASE_URL=http://127.0.0.1:8000 \
API_AUTH_TOKEN="$API_AUTH_TOKEN" \
dotnet test tests/automation/QualityLifecycle.Automation.csproj --filter "TestCategory=api|TestCategory=security"
```

Install the Playwright browser once before UI runs:

```bash
pwsh tests/automation/bin/Debug/net8.0/playwright.ps1 install chromium
dotnet test tests/automation/QualityLifecycle.Automation.csproj --filter TestCategory=ui
```

`QUALITY_LIFECYCLE_BASE_URL` defaults to `http://127.0.0.1:8000`. Security scenarios require
`API_AUTH_TOKEN` to be configured and only assert behavior; they never print its value.
