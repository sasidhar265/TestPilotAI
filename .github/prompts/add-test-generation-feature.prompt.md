---
mode: agent
description: Add a test-generation feature to the GitHub Copilot agent.
---

Implement the requested test-generation feature in this repository.

Requirements:
- Read `.github/copilot-instructions.md` and `app/models.py` first.
- Preserve the `TestDesignAgent` contract and `TestGenerationService` boundary.
- Keep GitHub Copilot as the only registered and implemented runtime.
- Preserve explicit user approval for Jira publication.
- Never expose credentials or include real personal data.
- Add or update pytest coverage.
- Run `pytest -q` and `python -m compileall -q app tests` before reporting completion.
