# API automation changes

Whenever adding or changing API tests, include the scenarios, executable C# bindings,
request builders, services and approved input data in the automation pack. Preserve existing
tests when adding new ones. Use System.Net.Http.HttpClient for C# API handling and the
approved quotation payload without invented fields. API-only packs do not need Playwright.

Use the shared folder structure in workspace/automation-standards.md. Keep step definitions
free of if/else, switch and ternary expressions; delegate varying behavior to strategies.

Run the affected API scenarios through ReqnRoll BDD, including newly added tests, before
reporting completion. Verify actual discovered/executed results; Python unit tests and C#
compilation alone do not demonstrate a BDD run. If target configuration is unavailable,
state which scenarios could not run. Do not claim repository smoke-test results cover
generated suites: execute the relevant pack in its configured test environment.

# Mandatory LLM models

Application agents using Codex AI / Codex CLI must use `gpt-6-astra` (GPT-6-ASTRA).
Application agents using GitHub Copilot must use `claude-haiku-4.5` (Claude Haiku 4.5).
Enforce these models in runtime calls as well as agent instructions, including retries
and repairs. Do not allow environment overrides or account defaults to change them.
See `.github/agents/model-policy.md` for route and fallback behavior.
