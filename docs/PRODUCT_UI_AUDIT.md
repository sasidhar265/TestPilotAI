# Product UI audit

Inspected: FastAPI routes and role middleware, SQLite SDLC lifecycle/records, vanilla
JavaScript page shell, six-stage test tools, eight-stage SDLC view, agent coordinator,
project queues, existing ReqnRoll and browser suites. Existing changes and user data preserved.

| Actual implementation | Product gap | Correction / dependency | Priority |
| --- | --- | --- | --- |
| Shared collapsible shell, theme, breadcrumbs, project selector | No fast record discovery or command navigation | Search within records; keyboard command palette | P1 |
| Versioned records edited by generic select/form; details are JSON | No approachable inline work surface | Reusable list/detail editor, named fields, source/versions/comments | P0 |
| Server lifecycle gates and version-bound approvals | Review context separated from human decision forms | Bring record workbench beside existing stage decisions; explain approval scope | P0 |
| Existing agent jobs, immutable documents and task outputs | No individual suggestion review connected to records | Server-validated task suggestions, durable human choices, explicit draft save | P0 |
| Item links and captured link versions | Raw IDs and missing drill-down | Navigable incoming/outgoing links and current-version indicators | P1 |
| Role metadata names editable kinds | Developer field restrictions known only on API failure | Return per-record editable fields; enforce existing backend rules | P0 |
| Work-item versions retained in SQLite | No history API or persistent clarification threads | Scoped detail endpoint, additive annotation table, audit events | P0 |
| Story/QA/release/documentation use same work-item service | Inconsistent interaction across phases | Apply shared editor, filters, history and discussions to every record kind | P1 |
| Pipeline evidence comes from configured local tools/human references | No general remote PR/pipeline synchronization | Preserve honest evidence source; configuration dependency remains | P2 |
| Documentation reference page and project documentation records | Two purposes unclear | Editable project documentation in contextual record workbench; reference help preserved | P1 |

No new frontend framework, simulated AI output, deployment, or destructive migration.

## Current implementation status

The inline record workbench, versioned clarification threads, source-validated AI task
review, keyboard command search, approval inbox filter, actionable project metrics and
traceability table are implemented. The shared editor supports backlog, development,
QA, release and documentation without separate copies of project records. Live external
PR/pipeline synchronization and per-role prompt/chat streaming remain integration work;
agent job state and retries continue through the existing execution infrastructure.
