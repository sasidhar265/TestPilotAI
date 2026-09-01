# Operations

## Required runtime

- Python 3.11 or newer
- GitHub Copilot CLI enabled by organization policy
- An authenticated Copilot user (`copilot login`) or `COPILOT_GITHUB_TOKEN`

The application deliberately has no fallback AI provider. A Copilot outage, authentication
failure, policy denial, exhausted allowance, or timeout is returned as a controlled error.
`COPILOT_TIMEOUT_SECONDS` limits each isolated specialist call. The larger
`COPILOT_COORDINATOR_TIMEOUT_SECONDS` limits the complete QA Master tool loop and must allow for
sequential automation, findings-driven revision, manual generation, validation, and storage.
In-flight specialist work is cancelled and awaited if the coordinator or user stops the request.

## Configuration

Copy `.env.example` to `.env`. Secrets must be supplied through the deployment platform's secret
store and must never be committed. `COPILOT_MODEL` is optional and must be allowed by the
organization’s Copilot policy.

Organizational memory is enabled by default at `.agent-memory/test_suites.db`. The directory is
ignored by Git. Back up, encrypt, retain, and delete this database according to the organization's
data policy. Set `ORGANIZATIONAL_MEMORY_ENABLED=false` to disable reuse.

Explicitly accepted test cases are stored beneath `ACCEPTED_OUTPUT_DIRECTORY` (`output` by
default). The server writes manual cases as the reviewer-selected CSV or Excel format, automation
cases as a `.feature` file, and a JSON acceptance receipt containing the reviewer, timestamp,
selected case IDs, suite hash, artifact hashes, and filenames. The directory and files use
restrictive local permissions where supported and are excluded from Git. Back up and retain this
directory according to the approved test-evidence policy.

For production, set `ENVIRONMENT=production`, provide a random `API_AUTH_TOKEN` of at least 32
characters through the secret manager, and set `ALLOWED_HOSTS` to an explicit comma-separated
allowlist. An identity-aware reverse proxy should authenticate users and inject
`Authorization: Bearer <API_AUTH_TOKEN>` only on the trusted upstream connection. Do not expose the
application container directly to users or put the shared upstream token in browser code.

The application bounds request bodies, uploaded files, total concurrent requests, and concurrent
Copilot generations. Tune `MAX_REQUEST_BODY_BYTES`, `MAX_UPLOAD_BYTES`,
`MAX_CONCURRENT_REQUESTS`, `MAX_CONCURRENT_GENERATIONS`, and
`REQUEST_QUEUE_TIMEOUT_SECONDS` from load-test evidence. The request-body limit must be larger than
the upload limit because multipart requests include framing.

## Health and verification

- `GET /api/live` is a process-only liveness probe.
- `GET /api/ready` checks configuration, the selected agent profile, and local memory access
  without consuming a Copilot premium request.
- `GET /api/health` reports the fixed runtime ID, authentication mode, memory entry count, and
  Jira configuration.
- `GET /api/generation/{request_id}/events?after={sequence}` returns bounded, incremental agent
  lifecycle events for the matching correlation ID. Events contain agent/action/status summaries,
  never the submitted requirement, generated test data, or credentials.
- `python -m pytest -q` runs the isolated test suite without external AI calls.
- `python -m compileall -q app tests` checks import and syntax integrity.

The health endpoint reports configuration, not upstream Copilot availability. Use a controlled
synthetic generation request for readiness checks only when consuming a premium request is
acceptable.

Terminate TLS and corporate SSO at the approved reverse proxy or ingress. The application emits
HSTS in production and restrictive CSP, framing, MIME-sniffing, referrer, permissions, and
cross-origin headers. Configure request limits at ingress as a second enforcement layer.

Run one application process per container while SQLite memory is enabled. For horizontal scaling,
replace repository-local memory with an approved managed data service or disable memory; do not
share a SQLite file between replicas. Centralize JSON stdout logs and alert on readiness failures,
HTTP 5xx/429/503 rates, latency, Copilot failures, Jira failures, and disk capacity.

## Release and rollback

Build an immutable image from a reviewed source revision, scan dependencies and the resulting
image, sign it, and deploy by digest. Keep the previous digest deployable for rollback. Before
promotion, verify `/api/live`, `/api/ready`, one controlled synthetic generation, cancellation,
export, and—where enabled—a non-production Jira publish. Database backup and restoration, incident
response, provider outage, credential rotation, and data deletion must be exercised outside this
repository before approval.

## Failure handling

- Never log prompts, generated test data, GitHub tokens, or Jira credentials.
- Return sanitized errors to clients.
- Do not automatically retry generation because retries consume Copilot premium requests.
- Jira publication must remain user initiated and must validate selected case IDs.
