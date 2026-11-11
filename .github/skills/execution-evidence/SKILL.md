---
name: execution-evidence
description: Interpret configured test runs and report discovered, executed, failed, skipped or unavailable evidence without treating generated code as a test result.
---

# Execution evidence

Use when planning a run, interpreting runner output or producing defects and metrics from evidence.

- Check the configured target and approved runner. The generated-suite execution plan requires a
  matching installed feature and a passing design gate; a list of scenario names is only a plan.
- Run only through the provided application action or authorized runner. Respect its timeout,
  cancellation, concurrency and environment boundaries; do not start processes from source text.
- Identify the project/pack, environment, run scope and result source. Read current runner artifacts
  such as TRX; distinguish outline definitions from expanded discovered/executed example cases.
- Report passed, failed, skipped, not run, cancelled and unavailable results separately. A successful
  build, Python unit test or unrelated repository run cannot certify a generated BDD pack.
- If target configuration, credentials, fixtures or runtime dependencies are missing, name the
  affected scenarios and what could not run. Do not replace failures with simulated passing results.
- Derive defects and metrics only from recorded observations. Keep credentials and session values out
  of output, and do not invent execution details when only a final operation summary is available.

See [execution guardrails](../../guardrails/execution-evidence.md) and the local
[runner](../../../app/agents/automation_execution_agent.py). This skill supplies interpretation and
reporting guidance; the Python runner still owns process execution and result collection.
