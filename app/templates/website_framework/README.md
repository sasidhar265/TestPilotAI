# Selenium C# BDD automation framework

.NET 10 LTS, Selenium WebDriver, ReqnRoll and NUnit. Each discovered public page has a named
page object in **Pages/**. `[FindsBy]` properties are lazily initialised with
`SeleniumExtras.PageObjects.PageFactory.InitElements` in Services/PageCatalogService.cs.
The navigation component initialises its own collection. No `[CacheLookup]` attributes
are generated; proxies re-locate elements while explicit waits handle page updates.
Reusable navigation lives in **Pages/Components/**. Page objects
encapsulate locators/actions; **Services/EvidenceService.cs** owns assertions. Bindings are
thin, scenario-scoped adapters with no conditional branches. Every scenario gets a fresh
browser, explicit waits, deterministic fixture data and cleanup.

## Where the tests are

| Suite | Feature | NUnit category | Scope |
| --- | --- | --- | --- |
| Smoke | Features/Smoke/Smoke.feature | Smoke | Public page availability and published titles |
| Sanity | Features/Sanity/Sanity.feature | Sanity | Published navigation, appearance selection and document readiness |
| Regression | Features/Regression/Regression.feature | Regression | Published headings, controls, dropdown options and page contracts |

Input/CaseData.Json contains the actual scenario IDs, names, categories, expectations and
page references. Input/PageObjects.Json maps concrete page classes to discovered URLs.
Input/Discovery.Json retains the source evidence. Input/Request.Json retains the prompt
and coverage limitations. Feature scenarios name the page and behavior they verify.
NUnit category metadata is in Reqnroll/TestCategories.cs; Gherkin files need no tags.

## Run

Requires .NET 10 SDK+, a browser and its matching driver. Selenium Manager can resolve drivers.
Run from the extracted framework directory:

```sh
dotnet restore Automation.csproj
dotnet test Automation.csproj --results-directory TestResults/Reports
dotnet test Automation.csproj --filter TestCategory=Smoke
dotnet test Automation.csproj --filter TestCategory=Sanity
dotnet test Automation.csproj --filter TestCategory=Regression
```

Category runsettings are also available, for example:
`dotnet test Automation.csproj --settings Reqnroll/Smoke.runsettings`.
The default command executes every discovered scenario, including all three suites.
TRX reports are configured in Reqnroll/Automation.runsettings. Failed scenarios attach
screenshots under TestResults/Reports. No report/pass status is fabricated on generation.

## Runtime configuration

Edit non-secret defaults in Input/TestData.Json. WEBSITE_BASE_URL optionally replaces the
observed origin with an approved test origin. BROWSER accepts chrome, firefox or edge;
HEADLESS accepts true/false. Chrome is the default. Other browsers require their installation
and must be validated in the target environment. CHROME_BINARY and CHROMEDRIVER_DIRECTORY
optionally select an existing Chromium installation and driver. TEST_RESULTS_DIRECTORY
optionally selects an absolute evidence directory. Keep credentials outside the pack.
The framework does not bypass TLS validation and does not automatically retry failing tests.

## Extend with approved journeys

Add page-specific actions to Pages/*Page.cs, shared controls to Pages/Components, and
business assertions to Services. Add executable scenarios to the appropriate feature and
CaseData entries with approved input. Keep bindings reusable. Builders is available for
approved request/form construction and is intentionally unused by this public-page pack.
Do not invent selectors, credentials or successful business outcomes. Authenticated or
state-changing journeys need their requirements, test accounts and approved target environment.

Selenium page-object guidance: https://www.selenium.dev/documentation/test_practices/encouraged/page_object_models/


## PageFactory dependency

Selenium's original .NET PageFactory was removed from its bindings. This pack uses
DotNetSeleniumExtras.PageObjects.Core 4.48.0 with matching Selenium WebDriver/Support
4.48.0. It is a community implementation, not built-in Selenium. PageFactory initialises
element proxies; page objects own interactions, and Services owns assertions.
See https://github.com/Dreamescaper/DotNetSeleniumExtras.Core for the package source.
