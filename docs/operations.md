# Operations

## Required runtime

- Python 3.11 or newer
- GitHub Copilot CLI enabled by organization policy
- An authenticated Copilot user (`copilot login`) or `COPILOT_GITHUB_TOKEN`

The application deliberately has no fallback AI provider. A Copilot outage, authentication
failure, policy denial, exhausted allowance, or timeout is returned as a controlled error.

## Configuration

Copy `.env.example` to `.env`. Secrets must be supplied through the deployment platform's secret
store and must never be committed. `COPILOT_MODEL` is optional and must be allowed by the
organization’s Copilot policy.

Organizational memory is enabled by default at `.agent-memory/test_suites.db`. The directory is
ignored by Git. Back up, encrypt, retain, and delete this database according to the organization's
data policy. Set `ORGANIZATIONAL_MEMORY_ENABLED=false` to disable reuse.

## Health and verification

- `GET /api/health` reports the fixed runtime ID, authentication mode, memory entry count, and
  Jira configuration.
- `python -m pytest -q` runs the isolated test suite without external AI calls.
- `python -m compileall -q app tests` checks import and syntax integrity.

The health endpoint reports configuration, not upstream Copilot availability. Use a controlled
synthetic generation request for readiness checks only when consuming a premium request is
acceptable.

## Failure handling

- Never log prompts, generated test data, GitHub tokens, or Jira credentials.
- Return sanitized errors to clients.
- Do not automatically retry generation because retries consume Copilot premium requests.
- Jira publication must remain user initiated and must validate selected case IDs.
