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

## Repository formatting

Run `make format` to align Python (including tools), frontend source, Markdown, YAML,
JSON inputs, and C# files. Run `make format-check` to verify formatting without rewriting
files. These commands require Python with the dev dependencies, Node.js/npm, and the .NET SDK.
The pinned Prettier version is downloaded by npm on its first run.

`.editorconfig` defines indentation and line endings; `.prettierrc.yaml` defines web and
Markdown formatting. Markdown prose and embedded code examples retain their intentional
line breaks. Keep XML project and runner configuration files indented with two spaces.
Gherkin uses two spaces for scenario headings, four for steps, and aligned Examples tables.

Preserve approved input values when formatting JSON. Upstream vendor distributions, generated
build output, runtime data, and binary documents retain their original formatting. Their
exclusions are recorded in `.gitignore` and `.prettierignore`.
