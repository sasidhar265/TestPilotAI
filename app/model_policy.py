"""Mandatory model assignments for the application's Codex and Copilot routes."""

CODEX_MODEL = "gpt-6-astra"
COPILOT_MODEL = "claude-haiku-4.5"
COPILOT_ROUTES = frozenset({"organization-default", "auto", COPILOT_MODEL})
