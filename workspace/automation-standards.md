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
