# Implementation progress

## 1. Workflow, identity and deployment controls

Problem: agent stage completion, artifact review and human project status had no shared
business state; owner-private storage prevented cross-role handoff; configuration alone
allowed deployment hooks to run.

Implemented: server-owned lifecycle policy, atomic revision-checked transitions, evidence
requirements, role ownership, human-session-only decisions and audit. Added stakeholder,
product owner, developer and release manager roles with safe account migration. Added
explicit project membership and shared run visibility/recovery. Staging/production command
execution now checks human gates, captured artifact versions and the implemented/tested
candidate revision. Agent workers stop at development, QA and release human handoff gates.

Files: app/lifecycle_workflow.py; app/services/project_lifecycle.py;
app/services/sdlc.py, sdlc_delivery.py, sdlc_tools.py; app/sdlc_routes.py;
app/roles.py, role_access.py, users.py; existing account form and labels.

## 2. Screens and traceability

Problem: dashboard and SDLC had disconnected state; backlog/development/QA/documentation
needed persistent linked work items rather than document-only status.

Implemented: lifecycle timeline, accountable action queue, missing-evidence indicators,
evidence/decision forms, historical audit and team management in the existing SDLC screen.
Dashboard queue uses the same service and opens the selected project. Added versioned
requirements, epics, stories, tests, defects, releases and documentation with source-version
links, cycle checks, readiness/assignment rules and transitive change impacts. Requirement
changes reset analysis; story/test edits can rewind but never advance the human workflow.
QA retest evidence is required for defect closure. Unclosed defects block sign-off/release.

Files: app/services/project_work_items.py; app/static/scripts/project-lifecycle.js;
existing sdlc.js and index.html; docs/SDLC_WORKFLOW.md, UI_SCREEN_MATRIX.md,
ROLE_PERMISSIONS.md, INTEGRATION_GAPS.md and architecture.md.

## 3. Verification and regression corrections

Added ReqnRoll scenarios, executable C# bindings, HttpClient services, request builders and
synthetic Input fixtures for human lifecycle decisions, concurrent/stale writes, missing
evidence, rejections, defects/retests, source impacts, linked work items, role denial,
dashboard consistency and agent/model contracts. Expanded account-role BDD fixtures.
Preserved all existing scenarios and quotation payloads. No generated suite was substituted
with repository smoke results.

Updated stale Python expectations for existing UI labels, configurable OpenAI model,
expanded agent catalogue and revised prompt wording. Existing testing-agent assertions
remain. Updated the older browser route fixture for the new lifecycle/work-item endpoints.

Validation results and remaining external dependencies are recorded in the final verification
section below. User configuration, secrets, project data and pre-existing working-tree
changes were preserved. No real provider generation or production deployment was performed.

## Final verification — 2026-10-16

- ReqnRoll: **41 passed, 0 failed, 0 skipped** against the isolated FastAPI server.
  TRX scenario names and outcomes were inspected: 12 existing SDLC cases, 20 role-access
  cases including all four new roles, and 9 lifecycle-governance cases.
- Default Python regression suite: **813 passed, 136 skipped, 1 warning**. Opt-in browser,
  C# and external checks were not claimed as part of that default run. Browser checks
  and the affected C# BDD pack were executed separately.
- Browser regression: initial broad run **84 passed, 3 failed**. After fixture corrections
  and a fast-submit race fix, the three affected cases were rerun and **all 3 passed**.
  Live coverage includes login, project creation, source save, evidence, human transition,
  rejection, record persistence, dashboard consistency and 390px mobile layout. Existing
  mocked SDLC cases cover pasted and uploaded BRD flows; broader navigation checks cover
  Chromium/WebKit, portrait/landscape, shared views and themes.
- Full Ruff lint, changed-file Python formatting, JavaScript syntax, compileall and the
  Python wheel build passed. Scoped mypy passed for all **10 changed backend modules**.
  Whole-repository mypy still reports **40 errors in 12 other modules**; it is not green.
- No real AI provider calls, generated application suite execution, external deployment,
  UAT or production validation were claimed. Those require target configuration and
  accountable human decisions. The local test fixtures explicitly label attestations
  as synthetic rather than external results.

Sanitized per-scenario evidence:
[verification/sdlc-validation-2026-10-16.json](verification/sdlc-validation-2026-10-16.json).

See INTEGRATION_GAPS.md for remaining record-reconciliation, remote-integration and
publication boundaries. These are exposed accurately rather than simulated.

## 4. UI consistency and usability — 2026-10-16

Problems: seven page shells had competing card/heading conventions, limited page
orientation and inconsistent table/form geometry. SDLC mixed primary decisions with long
history and team-management forms. The shared dropdown rule clipped multiple-selection
lists. Embedded documentation introduced duplicate page headings. Account role guidance
omitted the newer responsibilities.

Changes: all seven main page shells now load shared workspace-ui.css and
workspace-chrome.js. Added consistent breadcrumbs, purpose text, keyboard skip links,
card/table/badge geometry, responsive input sizing, reduced-motion handling and usable
multi-select lists. Existing teal/navy identity, routes and role enforcement remain.
SDLC now shows current progress and next action first, groups the action forms, and places
full timeline/history/team controls behind native disclosures. Forms needing a requirements
baseline are hidden until it exists. Added role-specific account help and corrected
embedded documentation heading levels. The standalone login/offline guide retain their
specialised layouts.

Files: seven app/static/\*.html shells; new shared CSS/script;
project-lifecycle.js; documentation.js; users.js; app/static/README.md;
UI_DESIGN_SYSTEM.md and UI_SCREEN_MATRIX.md. Browser coverage added in
tests/test_workspace_consistency_browser.py. Canonical account-route fixture corrected
in test_mobile_navigation_browser.py. Documentation asset-version expectation updated
in test_api.py. Corresponding HTTP coverage includes WorkspacePresentation.feature,
C# bindings, HttpClient service, request builder and Input/WorkspacePresentation.Json.

Validation:

- Shared layout/workspace/theme/SDLC browser batch: **18 passed**.
- Final shared-component checks with role guidance: **8 passed** (subset recheck).
- Chromium/WebKit phone-width navigation/dark-mode batch: **40 passed**, 36 deselected.
- Live lifecycle form, rejection, persistence and dashboard journey: **1 passed**.
- Actual /admin/users route recheck across shared and mobile fixtures: **5 passed**.
- ReqnRoll HTTP page contracts: **7 passed**, no failures or skipped scenarios. TRX
  scenario names/outcomes inspected. Fixed an old fixture pointing to /users rather than
  the actual /admin/users route.
- Default Python suite: **813 passed, 144 skipped, 1 warning**. Updated the stale
  documentation script cache-version assertion; no API business behaviour changed.
- Ruff, JavaScript syntax, pinned Prettier formatting and git diff whitespace checks passed.

Evidence: [UI verification](verification/ui-consistency-2026-10-16.json),
[account-page preview](verification/ui-users-desktop.png),
[documentation preview](verification/ui-documentation-desktop.png).

No backend business rules, user records, production environments or external integrations
were changed in this UI increment. Existing integration boundaries in INTEGRATION_GAPS.md
remain. This pass standardises presentation; it does not claim usability testing with
representative users or universal comprehension.

## 5. Sequential SDLC workspace — 2026-10-16

Problem: SDLC showed a progress panel, agent board and artifact ledger together, while the
existing requirements-to-test workflow had a clearer numbered sequence. Users needed one
focused step with its relevant tools, records and human handoff.

Implemented eight ordered groups: Requirements → Business approval → Backlog → Development
→ Quality assurance → Release readiness → Deployment → Closure. `PHASES` lives alongside
WORKFLOW in app/lifecycle_workflow.py. Snapshots expose the current group and complete
presentation metadata; every one of the 25 existing business states maps to exactly one
group. Existing state transitions, role rules and approval requirements are preserved.

The new sdlc-sequence.js consumes backend groups rather than duplicating state rules.
The UI reuses the existing numbered-step style, displays current and selected steps
separately, provides previous/next previews and a return-to-current action, and restores
`?phase=` views after refresh. Handoffs auto-select the next current group; rejection
selects the relevant rework group. Future/earlier previews show records and links, while
human evidence/decision actions remain on the current group. Step 1 contains the existing
requirements baseline and input link. Existing `?stage=` artifact routes are retained.

Records are filtered by the selected group's types, with documentation available throughout.
Unsaved record drafts block group switching and artifact-link navigation until explicitly
saved or cleared. Re-selecting the current tab preserves the draft. AI execution and agent
artifact inspection are expandable supporting tools. Active/blocked run changes reveal the
existing run controls. The sidebar entry is now labelled SDLC workflow across all seven
page shells. Phone layouts use an internal horizontal step bar; keyboard arrows/Home/End
and Enter provide equivalent navigation.

Files: app/lifecycle_workflow.py; services/project_lifecycle.py and sdlc_delivery.py;
static/scripts/sdlc-sequence.js, project-lifecycle.js, sdlc.js, sdlc-delivery.js and
workspace-pages.js; shared workspace-ui.css; seven page shells; the workflow/UI design
and screen documents. Added policy coverage and expanded browser tests. Added the
corresponding LifecycleGovernance ReqnRoll scenario, C# service assertion and approved
sequence fixture, using the existing HttpClient request builder and thin bindings.

Verification:

- **49 ReqnRoll scenarios passed**, no failures/skips: lifecycle gates, account roles,
  existing SDLC contracts, seven page contracts and the new sequence/rejection contract.
  Actual TRX scenario names and outcomes were inspected.
- Default Python suite: **814 passed, 145 skipped, 1 warning**. The 31 focused lifecycle,
  storage and delivery checks also passed. Opt-in cases are reported separately.
- Initial shared/workspace browser batch: **18 passed, 1 failed**. The live case exposed
  a project-creation race during initial loading; the affected controls now remain disabled
  until the pending operation finishes. Corrected live/legacy/keyboard batch: **4 passed**.
  Final live journey after draft-navigation protection: **1 passed** (overlapping recheck).
- Live coverage includes preview without advancement, current-step return, URL restore,
  BA handoff to stakeholder approval, rejection to clarification, automatic step selection,
  record/draft preservation, dashboard consistency and reload persistence.
- Responsive Chromium/WebKit SDLC checks: **8 passed**, 68 unrelated cases deselected.
- Scoped mypy passed for the three changed backend modules. Ruff, relevant Python and
  Prettier formatting, JavaScript syntax, compileall and diff whitespace checks passed.

Evidence: [sequence verification](verification/sdlc-sequence-2026-10-16.json),
[desktop preview](verification/sdlc-sequence-desktop.png),
[phone preview](verification/sdlc-sequence-mobile.png).

No live AI runs, generated target-suite execution, UAT or deployment was represented as
completed by navigation. Existing external-integration boundaries remain documented in
INTEGRATION_GAPS.md. No user data or environment configuration was replaced.


## Increment: one SDLC entry point and embedded requirements (2026-10-16)

Actual-versus-expected UI gaps and corrections:

| Existing problem | Expected experience | Correction / affected modules | Priority / dependency |
| --- | --- | --- | --- |
| Bare home opened requirements separately from SDLC | One numbered lifecycle starting at BRD | workspace-pages.js makes signed-in home open /sdlc; explicit tool URLs remain supported | P1 / existing lifecycle policy |
| Project selection lived only on requirements page | Select project throughout the journey | sdlc-sequence.js reuses controls above workflow steps | P1 / project loading |
| Step 1 linked away to source entry | Enter BRD and review baseline within Step 1 | Original editor relocated without duplicate IDs or handlers; returns to specialist source tool when requested | P1 / shared editor |
| Agent stages, testing tools and business stages competed in sidebar | Main workflow plus optional specialist tools | navigation.js shared by seven page shells; secondary disclosure preserves existing routes and permissions | P1 / existing navigation |
| Testing/provider settings dominated source entry | Clear source-save action with optional advanced controls | index.html, sdlc-sequence.js, workspace-ui.css; human gates unchanged | P1 / existing forms |

Verification and limitations are recorded below after execution. No backend API, approval rule, stored artifact or deployment configuration changed in this increment.

Verification for this increment:

- Python suite: **814 passed, 146 skipped, 1 warning** (opt-in browser cases run separately).
- Final shared-shell, source-editor and legacy testing browser batch: **20 passed**.
- Final live human lifecycle journey: **1 passed**; baseline save, stage decisions, rejection, dashboard consistency and refresh persistence verified.
- Responsive Chromium/WebKit SDLC checks: **8 passed**, 68 unrelated cases deselected.
- Existing ReqnRoll regression pack: **49 executed, 49 passed, zero skipped**. Actual TRX inspected, including seven shared-page contracts. No API tests or contracts were changed in this UI increment. These are repository regressions, not execution of generated target suites.
- Earlier browser runs exposed obsolete separate-page expectations and a test fixture that did not serve the new canonical `/sdlc` reload route. Expectations and fixtures now follow the actual UI, including opening optional settings before editing them.
- Ruff checks/formatting, changed JavaScript syntax and diff whitespace checks passed.

Review evidence: [verification record](verification/sdlc-entry-2026-10-16.json),
[desktop](verification/sdlc-entry-desktop.png), [phone](verification/sdlc-entry-mobile.png).
Remaining gaps: remote PR/build synchronization, durable conversion between generated
artifacts and project records, and external-service configuration remain as documented
in INTEGRATION_GAPS.md. The UI restructuring does not establish live service success.

## Increment: inline SDLC review workbench (2026-10-16, verified slice)

Audit and implementation plan: PRODUCT_UI_AUDIT.md, SCREEN_INTERACTION_MATRIX.md,
WORKFLOW_ALIGNMENT.md. The shared shell and authoritative lifecycle are preserved.

Implemented so far:

- Reusable searchable record list with an inline editor across requirements, backlog,
  development, QA, release and project documentation; optimistic saves use existing APIs.
- Additive annotation storage, project-scoped version-history/review APIs, human session
  checks, stale-write rejection and immutable version-bound clarification comments.
- Contextual AI panel reads actual versioned task artifacts and source references;
  use-in-draft/dismiss choices persist, source validity is checked on the backend,
  and using a suggestion requires a separate explicit record save.
- Backend field metadata reflects PO-owned story scope and developer status/reference
  permissions. Reviewers can read records and comment without receiving edit authority.
- Navigable incoming/outgoing traceability links and external evidence references.
- Explicit inline requirement amendment reopens analysis and invalidates prior approval.
- Shared keyboard command search (Ctrl/Cmd K) and current-project record discovery.

Files: project_reviews.py, sdlc.py, sdlc_routes.py, project_lifecycle.py,
role_access.py, project-lifecycle.js, workbench-shell.js, sdlc.js, shared UI stylesheet
and seven HTML shells; associated Python/browser and C# ReqnRoll automation pack.

Initial verification: 818 Python checks passed; 53 actual ReqnRoll scenarios passed,
including four new inline-review contracts. Shared/legacy browser regression: 20 passed.
Live BA/stakeholder journey and final regression checks are in progress. No live AI or
production deployment is inferred from these local fixtures.

### Final verification and subsequent shared-module increment

- **818 passed, 149 skipped, 1 warning** in the Python suite. Opt-in browser tests executed separately.
- **53 actual ReqnRoll scenarios passed**, no skips/failures, including four new inline-review API scenarios. Actual TRX result names/outcomes inspected. C# builders, service, bindings and synthetic Input fixtures are included; existing scenarios retained. Dashboard counts are checked against actual project records.
- **22 browser checks passed** across shared pages, legacy test-design tools, BRD ingestion, suggestion draft/save/dismiss and linked-defect creation.
- **2 live browser journeys passed**, including separate BA/stakeholder accounts, saved source, inline edits, discussion, approval of exact v2, explicit v3 amendment, invalidation and refresh persistence.
- **8 responsive Chromium/WebKit checks passed**, 68 unrelated cases deselected. These plus the above are **32 distinct browser cases**. Final focused recheck of four live/contextual journeys passed after the record-first layout adjustments.
- Ruff and formatting passed for affected Python files; scoped mypy passed for review, work-items, lifecycle and routes; changed JS syntax, scoped Prettier and diff whitespace checks passed. Vanilla JS has no separate frontend bundle build.

Root causes corrected during verification:

- BA project source saving attempted an unauthorized global rules write. Project source rules now persist in their versioned request without publishing shared rules or granting new permissions.
- Browser test CSP waits now use function predicates; CSP was preserved.
- Existing record-disclosure expectations now match the default-open inline workspace.
- Queue navigation waits for project context before opening the workspace; browser checks wait for this completed navigation.

Further implemented across modules: role-aware approval inbox, real dashboard record counts
with worklist drill-down, readable traceability table, source-linked defect drafts, project
member assignment suggestions, explicit requirement amendment, reduced irrelevant fields,
project-switch draft protection, and accessible shared command search. History and comments
are persisted; a suggestion choice alone never changes or approves a record.

Evidence: [verification](verification/inline-review-2026-10-16.json),
[desktop workbench](verification/inline-review-desktop.png),
[phone workbench](verification/inline-review-mobile.png).

Remaining gaps (not claimed complete): automatic extraction/conversion of all BRD/agent
outputs into governed work items; role-specific conversational AI/token streaming; general
remote PR/build/deployment synchronization and live environment configuration. The shared
record workbench and existing execution/evidence/gate controls remain functional across
backlog, development, QA, release and documentation. Tests do not establish execution of
generated target suites, live UAT, or a production release. No production deployment,
configuration overwrite, user-data deletion or destructive migration was performed.
