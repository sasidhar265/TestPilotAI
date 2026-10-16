# Actual versus expected audit

Inspected 2026-10-16. Existing uncommitted SDLC implementation is preserved.

| Area / actual                                                                     | Expected / correction                                                                   | Modules                                           | Priority / dependency          |
| --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------- | ------------------------------ |
| FastAPI, vanilla JS shared shell, SQLite stores; seven agent stages               | Keep stack; add authoritative human lifecycle separate from agent run status            | services/sdlc*, sdlc_routes, static/scripts/sdlc* | P0                             |
| Immutable project revisions and reviews, optimistic writes                        | Atomic guarded transitions, current-baseline approvals, rejection and audit             | services/sdlc, lifecycle workflow                 | P0                             |
| Owner-private projects                                                            | Explicit project membership plus existing account roles                                 | users, roles, role_access, sdlc_routes            | P0                             |
| BA + four testing roles + admin                                                   | Add stakeholder, PO, developer, release manager without changing existing role meanings | users, roles, users UI                            | P0                             |
| Server-configured build, preview, staging, production commands and receipts       | Human release gates checked when commands execute; no configuration-only approval       | sdlc_delivery, sdlc_tools                         | P0                             |
| /sdlc stage ledger and agent board; /project-dashboard uses separate STLC records | Shared lifecycle state and role queue visible in existing screens                       | index, sdlc UI, dashboard                         | P1 / workflow                  |
| / requirements upload, BA validation, stories, scenarios, test generation         | Versioned human handoffs across requirements, backlog, sprint, QA, release              | workflow.js, sdlc routes, workflow UI             | P1 / workflow                  |
| STLC requirement/test/defect store and SDLC revisions are independent             | Explicit versioned links and change-impact flags; eventual durable record-ID bridge     | services/stlc, sdlc                               | P1                             |
| /documentation is reference material; saved artifacts in ledger /knowledge        | Project documentation and source links accessible throughout lifecycle                  | sdlc ledger, documentation                        | P1                             |
| Copilot/Codex provider policy already enforced by model_policy                    | Preserve gpt-6-astra / claude-haiku-4.5 on retries and repairs                          | model_policy, agent runners                       | Existing; regression           |
| No general remote PR/build synchronisation                                        | Show supplied evidence as human attestation; never pretend provider verification        | Jira, sdlc_tools, release UI                      | P2 / credentials and contracts |
| Existing repository ReqnRoll pack, Python and opt-in Playwright checks            | Execute changed pack against isolated server; record actual counts                      | automation, tests                                 | P0 / implementation            |

External execution requires configured provider access, repository, build/preview commands,
target environment and deployment receipts. Local checks cannot establish a real production release.

## Implemented corrections

P0 workflow, current-baseline human decisions, cross-role project membership, new account
roles, server-side role checks and command-boundary release controls are implemented.
P1 shared lifecycle queue, timeline, persisted linked records and source-change impact
indicators are implemented in existing screens. API and browser evidence is recorded in
IMPLEMENTATION_PROGRESS.md.

## Remaining boundaries

- Agent artifacts and STLC records retain their existing IDs and version histories. Human
  users can link their references to project work items. Automatic conversion/reconciliation
  across these stores is not implemented; importing or overwriting user records by heuristic
  name matching would be unsafe.
- PR/build/pipeline references entered in project records are human attestations. They are
  not a newly installed remote Git integration. Existing configured command evidence remains
  separately visible; live remote synchronisation requires a chosen provider and credentials.
- Project documentation is versioned and traceable in the project workspace; the existing
  /documentation page remains a reference centre. Automatic publication is not performed.
- Live AI generation, generated-suite execution against its target application, real UAT,
  staging and production verification require configured providers/environments and human
  approvals. Unit fixtures and local BDD attestations do not establish those outcomes.
- Whole-repository mypy has existing errors outside the changed workflow modules. Scoped
  type checking covers all ten changed backend modules successfully.


### UI entry correction (2026-10-16)

Requirements entry now sits within SDLC Step 1; bare signed-in home opens the
workflow. Project selection remains visible across steps, and specialist tools are
secondary navigation. This resolves the split entry experience without replacing
existing editors, APIs, stored records or human approval gates. External integration
and generated-artifact conversion gaps above remain open.

### Inline product workbench increment

Completed: inline record editing, version-bound review threads, contextual review of
existing agent tasks, explicit suggestion-to-draft save, linked-defect creation, record
history/traceability, approval inbox filtering and real project-record dashboard counts.

Still open: structured extraction of every BRD finding into individual requirement
records; provider-backed conversational assistance/token streaming in every role panel;
remote PR/build/deployment synchronization beyond configured local tools and supplied
references; automatic conversion of every agent output into governed backlog/test records.
These are not represented as completed integrations. Existing agent run/retry controls
and target-environment execution remain available under their original configuration gates.
