# Automation coding standards

Edit this file to define the team's conventions for all generated automation languages.

- Use idiomatic names, reusable step definitions, and scenario-scoped state.
- Separate bindings, clients/page objects, fixtures, and configuration.
- Read URLs, credentials and environment-specific values from runtime configuration.
- Never invent business rules, API contracts, selectors, fixture values or passing assertions.
- Full packs must implement every step, include dependency/setup instructions, and fail clearly
  when required configuration is missing. No pending steps, empty bodies or placeholder code.
- Bindings-only output deliberately contains pending method declarations for developers to fill.
- Do not put tags in feature files. Preserve Given/When/Then behavior and outline parameters.
- Generated code needs review and compilation/testing in its target environment.

## Required framework structure (every language)

Use these sibling folders under the automation framework root:

```text
Reqnroll/                 runner configuration and language discovery adapters
Features/                 *.feature
StepDefinitions/          *StepDefinition.<language extension>
Hooks/                    Hooks.<language extension>
TestContext/              testcontext.<language extension>
Services/                 *Service.<language extension>
Builders/                 *builder.<language extension>
Models/                   *Model.<language extension>
Utilities/                *Utility.<language extension>
TestResults/Reports/      actual execution reports
Input/                    TestData.Json and CaseData.Json
```

Keep project/dependency manifests and README.md at the root. Retain `Reqnroll` as the
configuration folder name for all languages, while using the selected language's BDD runtime.
Use appropriate extensions (.cs, .java, .py, .js, .ts, .rb). Do not generate alternate
Support, src/test, or lowercase features trees. Populate each role's folder as its artifacts
are created; document unused folders rather than generating fictitious business code.

Regenerate Features/generated.feature and Input data from the current approved suite.
Include every new API automation scenario alongside the suite's existing scenarios, with
its executable bindings, approved fixtures and required helpers. The default C# BDD command
must discover and execute the entire pack without an opt-in test filter. Verify new API
tests through ReqnRoll execution; compilation or repository smoke results are insufficient.
Input/TestData.Json contains unambiguous JSON request fixtures by name, preserving numeric
precision; Input/CaseData.Json preserves all case-specific test data, including plain text.
Read fixture data from Input, keep runtime secrets outside the pack, and write real execution
output under TestResults/Reports. Configure discovery/imports and hooks for this layout.
Python packs run with `python Reqnroll/run.py`, which stages Behave's required discovery tree
in a temporary directory; authored files remain in the shared layout.


## Request builders and strategies

For every C# automation pack, handle API requests with `System.Net.Http.HttpClient`.
Put HTTP operations in typed clients in Services, using injected HttpClient instances from
`IHttpClientFactory`/`AddHttpClient`. Build `HttpRequestMessage` bodies from the approved request
builder and send asynchronously with cancellation support. Preserve response status, headers,
and body for assertions, including non-success responses. Configure URLs and credentials at
runtime. Do not use RestSharp, Flurl, WebClient/WebRequest, or Playwright API request contexts
for C# API handling. Playwright remains available for browser UI automation.

For quotation/finance endpoint requests, the user-approved payload is
`app/templates/framework/QuotationRequest.Json`, exported as `Input/QuotationRequest.Json`.
It overrides older BRD request-shape examples and generated/cached assumptions. Preserve the exact
Outlet/Finance/Vehicle/Parameters fields and spelling, including `Outlet.code` and
`Vehicle.VehicleRegstrationDate`. Never append customer, eligibility, maintenance, oracle or
version metadata to this payload. Keep those concepts in separate test context where needed.
Use a typed fluent `QuotationRequestBuilder` with the supplied payload as its default; customize
only known fields with explicit supplied test data. No inferred request values or business formulas.

Across all languages, step definitions are thin adapters: no if/else, switch/match/case, unless,
or ternary conditional expressions. Delegate varying behavior to small injected strategies,
and keep transport, parsing and validation in services/utilities. Avoid large conditional
strategy dispatchers and avoid unnecessary strategy classes for behavior that does not vary.
Static generation/download checks reject branching in StepDefinitions; target-language
compilation and execution still need to be verified for each generated pack.
