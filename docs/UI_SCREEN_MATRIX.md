# Screen alignment matrix

| Screen / existing destination                            | Current authoritative content and actions                                                                                              | Remaining integration                                                        |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Dashboard /project-dashboard                             | Project lifecycle queue uses same backend state as SDLC; identifies accountable role and pending gates; opens selected project         | Existing STLC metrics retain separate record identities                      |
| Requirements /?view=requirements                         | Embedded in SDLC Step 1: existing upload, versioned save and BA review; advanced generation options remain available                                       | Human requirement records are linked explicitly in SDLC                      |
| Backlog /?view=stories and /sdlc                         | Existing AI stories; versioned epics/stories, criteria, priority, estimate, dependencies and refinement notes in project record editor | Automated conversion of every generated story to a work item remains pending |
| Developer /sdlc?stage=development                        | Existing implementation/build evidence plus assigned story, sprint, status and PR/build references                                     | Remote Git provider synchronisation requires configured integration          |
| QA /sdlc?stage=testing, /progress, /quality-lifecycle    | Existing tests/results; linked test/defect records; guarded QA sign-off and defect retest loop                                         | Automatic SDLC-to-STLC record-ID reconciliation remains pending              |
| Release /sdlc?stage=release                              | Human UAT, release and production gates, checklists, rollback references; existing real command receipts                               | Live environment validation requires server configuration                    |
| Documentation /documentation and project artifact ledger | Existing reference centre plus versioned project documentation records linked throughout lifecycle                                     | Publication workflow and automated report reconciliation remain pending      |
| Agents /sdlc                                             | Existing seven-agent catalogue, configured dependencies, execution events and source-versioned outputs                                 | Generated outputs remain suggestions until human decisions                   |

The shared SDLC panel reuses existing shell, cards, forms and navigation. It includes
server-sourced timeline and criteria, accessible status/error announcements, evidence and
decision forms, team membership, work item editing and audit. No duplicate standalone pages.
All user-supplied text renders via textContent/form values. No demo project records are seeded.

## Visual consistency update

The seven main page shells now share workspace-ui.css and workspace-chrome.js: common
breadcrumbs, purpose text, surfaces, cards, table spacing, badge geometry, focus patterns
and responsive form sizing. The SDLC panel prioritises the current stage and next action;
workflow history, team management and records use progressive disclosure. Documentation
heading levels were corrected. See [UI_DESIGN_SYSTEM.md](UI_DESIGN_SYSTEM.md) for conventions.

## Sequential SDLC workspace

The `/sdlc` workspace now uses the same numbered-step presentation as the existing
requirements-to-test-design flow. These groups are metadata in the backend workflow
policy, not a second set of frontend transition rules.

| Step | Workspace         | Main work                                                               |
| ---- | ----------------- | ----------------------------------------------------------------------- |
| 1    | Requirements      | BRD upload, analysis, BA validation and clarification                   |
| 2    | Business approval | Attributable stakeholder decision                                       |
| 3    | Backlog           | Story generation/refinement, priority, estimation and sprint assignment |
| 4    | Development       | Architecture evidence, implementation, PR review and build checks       |
| 5    | Quality assurance | Test design/execution, defects, retests and QA sign-off                 |
| 6    | Release readiness | UAT, checklist, rollback planning and release approval                  |
| 7    | Deployment        | Staging, production approval, deployment and verification               |
| 8    | Closure           | Release notes, operational handover, documentation and closure          |

Previous/next controls and keyboard-accessible tabs change the view only. Upcoming and
earlier steps show relevant records and links; evidence and human-decision forms remain
on the current backend stage. The current-step marker remains separate from the selected
preview tab. Handoffs select the next current step automatically; rejection selects the
correct rework group. `?phase=` restores a reviewed step after refresh. Existing `?stage=`
artifact links still work. Agent execution and artifact inspection remain expandable
supporting tools rather than additional competing lifecycle steps.


### Main entry and requirements amendment (2026-10-16)

Signed-in bare home opens `/sdlc`. Project selection stays above all eight numbered
steps. Step 1 contains the existing editable BRD/requirements form, attachment tools,
BA review, version-save action and baseline summary. Advanced test-generation and
AI delivery options use disclosures. The same editor supports the compatible
`/?view=requirements` specialist route; navigation preserves its draft in memory.
Specialist stage links remain available under the shared sidebar's “Specialist tools”.

### Inline product workbench amendment

Requirements, backlog, development, QA, release and project documentation now share
searchable record lists, inline details, version history, discussions and traceability
links. Real agent task suggestions can be reviewed into an unsaved draft or dismissed;
a separate Save persists changes. The project dashboard exposes real record counts and
filtered action/approval queues. Ctrl/Cmd K searches workspaces and current-project
records. See SCREEN_INTERACTION_MATRIX.md for API and permission mapping, and
IMPLEMENTATION_PROGRESS.md for verified journeys and remaining integration gaps.
