# Role workflow audit — 2026-10-16

This increment audits the existing implementation and preserves the substantial
uncommitted SDLC work already present. It changes working interactions in the existing
JavaScript screens; it does not introduce mock screens or claim earlier work as new.

## Walkthrough and findings

| Role / handoff | Reviewed behavior and evidence | Correction in this increment |
| --- | --- | --- |
| BA → stakeholder | Requirements source, versioned record editing, clarification discussion, exact-version approval, explicit amendment and invalidation. Live signed-in browser journey against temporary stores. | Hide previous record's discussion/actions until the selected detail request succeeds. Disable editing while permissions load; ignore obsolete detail failures. |
| Product Owner → developer | Linked backlog records, refinement gates, saving and reloading references. Real local store browser fixture and signed-in ReqnRoll permission scenarios. | Cross-kind traceability opens the appropriate step and expands the record workbench rather than leaving the record under an unrelated phase. |
| Developer → QA | PO-owned story fields remain restricted; implementation references save and reload. Role-specific browser and backend enforcement checks. | New-record choices exclude PO-owned story creation. Existing story status/reference editing remains available. |
| QA → developer → QA sign-off | Linked defect drafts, rework, required passing retest evidence, stale writes, traceability and approvals. Browser, backend and actual ReqnRoll execution. | Prevent stale record review actions and avoid re-enabling restricted submit controls when another operation finishes. |
| Release Manager → closure | Release reference persistence, human approvals, candidate/version checks, deployment command gates and complete lifecycle traversal. | Closed projects display Completed rather than Work in progress. |
| All roles | Shared editor, project queue, command search, phase navigation and browser history. | Protect unsaved drafts on programmatic navigation, back/forward and page unload. Search stops its record-opening action when a dirty draft prevents opening. |
| AI output → human record | Source/version-bound suggestions, explicit use-in-draft/save and persistent dismiss decisions; provider model enforcement and agent handoff/recovery regression tests. | Pending record requests cannot expose another record's suggestion controls. Applying a suggestion remains a draft until explicitly saved. |

The authoritative role/approval restrictions remain on the server. Client improvements
prevent dead ends and misleading interactions; they do not grant new permissions.
Cross-step record discovery deliberately leaves previous requirements read-only until
an authorized analyst selects the existing explicit amendment action.

## Verification

- Python suite: **818 passed, 153 skipped, 1 collection warning** with explicit isolated
  authentication settings. Opt-in tests are verified separately below.
- Actual existing ReqnRoll pack: **53 passed, 0 failed, 0 skipped** on an isolated local
  server. TRX names/outcomes were parsed and checked: 12 agent-driven SDLC scenarios,
  14 lifecycle governance scenarios, 20 role/access scenarios and 7 page contracts.
- Live browser: **2 passed**, BA/stakeholder approval/amendment and lifecycle evidence,
  rejection, persistence and draft protection.
- Frontend regression: **19 passed, 0 failed**. It exercises real temporary SQLite services through browser
  request fixtures, with explicitly synthetic AI tasks and evidence. It verifies pending
  review response behavior, suggestion draft/save/dismiss, linked defects, cross-phase
  links, role-specific edit/save/reload, restricted story creation and closed status.
- Ruff and JavaScript syntax checks pass. There is no separate frontend bundle build.

The first unrestricted-configuration Python run returned authentication failures because
local configuration protected the app; rerunning with test-only explicit settings passed.
The first BDD page run lacked a signed browser session for Manage users; the final run
uses a signed synthetic admin session and passes. Chromium and the .NET test host require
execution outside the macOS sandbox. No user configuration was overwritten.

Sanitized scenario evidence: [role-workflow-audit-2026-10-16.json](verification/role-workflow-audit-2026-10-16.json).

## Open integrations and limits

This audit does **not** establish that every integration is complete. Existing gaps remain:

- Automatic conversion/reconciliation of every BRD finding and generated agent task into
  governed requirement/backlog/test records. Existing explicit record creation and
  suggestion-to-draft review work, but are not an automatic extraction pipeline.
- Provider-backed conversational assistance and streaming in every role panel.
  The contextual panel reviews existing agent outputs; it is not a conversational agent.
- General remote PR/build/deployment synchronization. Supplied references remain human
  attestations; configured command receipts are separate evidence.
- Live AI generation, execution of a generated suite against its own configured target,
  actual UAT, staging and production verification were not exercised in this increment.
  Repository BDD results do not establish those external outcomes.

See [integration gaps](INTEGRATION_GAPS.md) for existing implementation boundaries.
These remaining capabilities require further implementation and/or target configuration;
visual appearance and local fixtures are not completion evidence for them.
