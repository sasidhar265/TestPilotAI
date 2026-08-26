# Contributing

1. Create a focused branch and keep changes scoped to one concern.
2. Preserve typed Pydantic boundaries and dependency injection for external systems.
3. Keep GitHub Copilot as the only AI runtime; the registry must remain fail closed.
4. Mock Copilot and Jira in automated tests. CI must never consume AI requests.
5. Run `make quality`. It enforces formatting, linting, type safety, tests, branch coverage, and
   import compilation.
6. Document configuration, operational, or architectural changes.

## Definition of done

- Public behavior has tests, including failure paths and authorization boundaries.
- `ruff check`, `ruff format --check`, `mypy`, coverage, and compilation pass locally.
- Customer requirements, generated suites, tokens, and Jira data never appear in logs or fixtures.
- New external dependencies have a clear owner and purpose and pass `pip-audit`.
- API changes remain backward compatible or include an explicit migration plan.
- Architecture decisions that change boundaries, runtimes, storage, or trust are recorded in
  `docs/architecture.md` or a focused ADR.

Pull requests should describe user impact, security considerations, verification, and rollback.
AI-generated output requires human review.
