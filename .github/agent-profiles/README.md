# Agent profiles

Profiles customize the shared Markdown agents for a team, product, or project without changing
Python. Copy `testpilot/` to a lowercase profile name, edit `profile.md`, and optionally add files
named after a base agent, such as `manual-test-generator.md`, `automation-test-generator.md`, or
`quality-gate.md`. Select it with `AGENT_PROFILE=<directory-name>`.

Place reviewed project baselines in an optional `knowledge/` directory. All Markdown files in that
directory are loaded in deterministic filename order as project knowledge. Keep them concise,
version-controlled, free of secrets or personal data, and traceable to an approved source version.

Base policies remain mandatory. Profiles can add domain terminology, risk priorities, supported
frameworks, traceability conventions, and output expectations, but cannot disable validation,
security, or explicit Jira authorization enforced by the application.
