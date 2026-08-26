# Engineering standards

## Ownership and boundaries

- `app/agents/` owns one-purpose functional agents and immutable capability metadata.
- `app/services/` owns orchestration and cannot depend on HTTP transport details.
- `app/main.py` owns request/response translation only; business rules belong below it.
- `app/models.py` is the validated contract boundary for requests, model output, and integrations.
- Outbound providers must be injected or mockable. Tests and CI must never consume Copilot or Jira.

## Required quality gates

Every change must pass `make quality`, which includes:

1. Ruff formatting and linting.
2. MyPy type checking for all application modules.
3. Unit and API tests with branch coverage of at least 75 percent.
4. Python bytecode compilation.
5. CI dependency vulnerability auditing with `pip-audit`.

Coverage is a risk signal, not a substitute for meaningful assertions. Security, storage,
provider failures, and irreversible outbound actions require explicit negative tests.

## Security and privacy

- Treat uploaded requirements and generated tests as confidential organizational data.
- Never log request bodies, prompts, document text, test data, or credentials.
- Accept only allowlisted document extensions and enforce byte, character, and image limits.
- Treat Copilot output as untrusted and validate it before storage, rendering, or publication.
- Preserve explicit human authorization for Jira and future external writes.
- Run containers as a non-root user and provide secrets only through the deployment platform.
- Apply retention, backup, encryption, and deletion policy to organizational-memory storage.

## API and operations

- Return validated Pydantic schemas and sanitized client-facing errors.
- Propagate or generate `X-Request-ID`; use it for operational correlation without payload logging.
- Keep `/api/health` inexpensive and free of premium or external calls.
- Use bounded timeouts for every network integration. Do not automatically retry premium AI work.
- Maintain backward compatibility for published endpoints unless a versioned migration is agreed.

## Dependency policy

- Pin direct dependencies to a compatible major-version range.
- Prefer maintained libraries with a narrow, documented purpose.
- Add dependencies through `pyproject.toml`, never through undeclared workstation state.
- Review vulnerability-audit failures rather than suppressing them globally.

## Release and rollback

- Build the same application artifact tested in CI.
- Deploy immutable images and inject environment-specific configuration at runtime.
- Backward-compatible code rollback must not require destructive storage changes.
- Database schema changes require forward and rollback procedures before deployment.
