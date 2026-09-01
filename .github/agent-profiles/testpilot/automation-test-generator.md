# Quality Lifecycle Studio automation override

Produce portable Cucumber Gherkin suitable for SpecFlow and comparable automation frameworks.
Use a Scenario Outline only when multiple data rows execute the same behavior, and always provide
a complete Examples table. Keep steps implementation-neutral so framework bindings can be reused.
Prioritize authentication, session state, permissions, API contracts, boundaries, and regression
flows that are deterministic and valuable to rerun.
