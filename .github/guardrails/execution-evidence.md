# Validation and execution evidence

Keep artifact generation, schema/layout validation, compilation, human review and target execution
separate in every report. Report only observations from the current operation; no generated
assertion, build success or historical note is evidence of an executed passing test.

For C# API work preserve System.Net.Http.HttpClient, the shared pack layout and the approved input
contract. Include scenarios, executable bindings, builders, services and approved data together;
keep step definitions free of branching. API-only packs do not need a browser dependency.

Run affected ReqnRoll scenarios in the relevant configured environment when asserting an API pack
works. Verify discovered/executed case counts and current result artifacts. Name scenarios that
could not run because configuration or evidence is missing. Repository smoke tests and Python unit
tests must never be relabeled as generated-suite execution results.

The configured generated-suite execution path requires source alignment, a matching installed
feature and a passing design gate. Respect runner locks, bounded timeouts, cancellation and
approved environment forwarding. Keep failures, skipped, cancelled and not-run outcomes visible.

Enforcement: layout/implementation validators, `app/workflow_routes.py` and
`app/agents/automation_execution_agent.py` own executable checks and result collection. These
instructions do not install missing targets, replace real execution or grant production access.
