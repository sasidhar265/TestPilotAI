# Test design artifacts

This directory contains review-ready test designs derived from
`docs/company-solution-requirements.md`.

- `manual-test-cases.xlsx` contains human-executed cases with preconditions, numbered actions,
  expected results, synthetic test data, and requirement traceability.
- `automated-features/*.feature` contains SpecFlow-compatible Gherkin candidates for deterministic
  API and pipeline behavior.

These artifacts are design inputs, not evidence of execution. Review environment-specific values,
step bindings, security policy, and Jira configuration before use.
