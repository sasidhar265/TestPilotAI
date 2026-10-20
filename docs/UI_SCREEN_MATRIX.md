# UI screen matrix

Existing vanilla JavaScript views and FastAPI routes are retained. No duplicate application or replacement framework is introduced.

| Screen | Existing route | Authoritative data / actions | Current correction |
| --- | --- | --- | --- |
| Project dashboard | `/project-dashboard` | `/api/sdlc/queue`, lifecycle stages, missing evidence, role action queues, linked record counts | Shared lifecycle queue reflects backend decisions; existing STLC summaries remain separate |
| Requirements | `/sdlc?phase=requirements` and compatible `/?view=requirements` | Upload/Jira, explicit LLM validation, server review records, saved BRD baseline, report download | Header project link opens project management in Documents; Requirements hides duplicate setup controls and persists the exact reviewed source before handoff |
| Business requirement approval | `/sdlc?phase=business-approval` | Lifecycle `approval_context`: exact BRD, BA/domain/alignment, requirement versions, comments and decision history | Focused review content plus existing authenticated human decision form |
| Backlog / refinement | `/sdlc?phase=backlog` | Versioned epics/stories, acceptance criteria, estimates, priorities, dependencies and sprint assignments | Reuse existing workbench and backend readiness rules |
| Developer workspace | `/sdlc?phase=development` | Assigned stories, immutable agent outputs, repository/PR/build evidence references | Existing stage ownership and configured tools retained |
| QA workspace | `/sdlc?phase=qa`, scenarios/test-cases/automation/execution specialist URLs | Test design, approved automation packs, configured BDD results, defects, retest and QA sign-off | Existing executable evidence and role gates retained |
| Release management | `/sdlc?phase=release`, `phase=deployment`, `phase=closure` | UAT, readiness, rollout/rollback evidence, release/production human approval, deployment history | Existing revision-bound guarded tools retained; no simulated deployment |
| Documents / versions | `/sdlc?view=documents` | Project revisions, source links and reviews | Versioned documents remain visible throughout the lifecycle |
| AI agent management | Existing SDLC AI activity disclosure, `/usage`, `/logs`, `/api/agents` | Role descriptors, configured model policy, real agent events, generated artifacts, blockers | New server BRD review provenance is distinct from human approval |
| Guidance | `/documentation`, `/static/user-guide.html`, `/docs`, `/knowledge` | Application docs, API reference, approved saved outputs and reference knowledge | Existing navigation and accessibility patterns retained |

Sidebar phases come from the backend policy. Business approval is a review preview until the backend reaches stakeholder approval. Empty, unavailable, stale-source and read-only states must identify their actual condition. UI buttons do not override entry/exit gates.
