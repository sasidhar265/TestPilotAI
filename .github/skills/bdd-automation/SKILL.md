---
name: bdd-automation
description: Generate or validate executable BDD automation packs from supplied suites and approved contracts, including bindings, builders, services and input data.
---

# BDD automation

Use for automated cases or executable pack implementation. Do not force automation onto manual cases.

- Preserve the accepted suite's case IDs, Gherkin and requirement mappings. Use Scenario Outlines when
  behavior differs only by data; every placeholder needs a complete, compatible Examples column.
- Follow [automation standards](../../../workspace/automation-standards.md) and
  [feature standards](../../../workspace/feature-standards.md). Include feature scenarios, executable
  bindings, request builders, services, approved fixtures and required build configuration together.
- For C# API handling use `System.Net.Http.HttpClient`, directly or through `IHttpClientFactory`.
  Preserve non-success responses for assertions. API-only packs do not require Playwright.
- When quotation behavior is in scope, use the approved
  [quotation payload](../../../app/templates/framework/QuotationRequest.Json). Preserve its exact
  field names; introduce no customer, oracle or version fields. Other services keep their own contract.
- Keep step definitions as thin adapters without if/else, switch/match or ternary expressions.
  Put transport, parsing, assertions and genuinely varying behavior in services or injected strategies.
- Supply meaningful assertions, independent expected results and explicit fixture/configuration gaps.
  Do not generate pending bindings, empty methods, invented endpoint paths or passing placeholders.
- Keep credentials and deployment URLs in runtime configuration. Keep source files inside the approved
  pack layout and preserve existing tests when extending a pack.
- Distinguish generation, structural validation, compilation and execution. Report actual discovered
  and executed BDD cases only after running the relevant pack in its configured environment.

See [execution evidence](../../guardrails/execution-evidence.md). A repository smoke run is not an
execution result for the generated customer suite.
