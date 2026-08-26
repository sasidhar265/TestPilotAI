# Copilot instructions for Story-to-Tests Agent

This is a Python 3.11+ FastAPI application. Keep API payloads typed with Pydantic and keep
GitHub Copilot generation, Jira, export, and web concerns in their existing modules.

- Preserve the four exact categories: `critical`, `smoke`, `sanity`, and `regression`.
- Treat model output as untrusted: require structured parsing and schema validation.
- Generate synthetic data only. Never log API keys, Jira tokens, story contents, or test data.
- Keep Copilot and Jira credentials server-side and sourced from environment variables.
- GitHub Copilot SDK is the only permitted AI runtime. Do not add OpenAI, GitHub Models,
  Ollama, mock, BYOK, or other model-provider adapters.
- Jira publishing must remain an explicit user action; generation must never auto-publish.
- Add tests for changed validation, export, and integration behavior. Mock all external APIs.
- Do not claim AI-generated cases are complete; maintain the human-review language in the UI.
- Prefer small services with dependency injection so external clients can be replaced in tests.

Before completing a change, run `pytest` and manually consider negative/error paths.
