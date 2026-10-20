# Inline Business Analyst review

## Repository inspection and implementation scope

The existing `BusinessAnalystAgent` already retrieves effective approved business sources,
the configured auto-finance pack and scoped in-house UK finance guide excerpts. It uses
the application's provider runner, mandatory Codex/Copilot model policy, citation checks
and usage recording. Requirements validation produces a summary and alignment assessment.
The source request is saved as a versioned project artifact before the BA-stage handoff.

Previously, the BA screen displayed those reports and a separate manual workbench. AI
findings had no stable review records or per-finding decisions. The minimal implementation
adds a typed review output, version-bound background run, review decision history and
human BA sign-off to that screen. Existing reports, requirement work items, approvals,
membership rules and business-stage transitions remain in place.

## User flow

1. Upload/read and validate the BRD in Requirements. Continue to BA review & approval.
   **Next stage** saves the validated source as the project's versioned BRD baseline;
   no separate **Save requirements** action is needed. Inspect that saved source under
   **BRD baseline** in the BA business overview. AI analysis reads this saved version,
   and supporting requirement drafts are retained in downloadable review history.
2. In **AI suggestions and BA feedback**, select **Generate AI suggestions**. The server
   reads the saved project baseline, not a new
   browser copy. The selected provider is inherited from that baseline.
3. Inspect BRD sections and requirements on the left, original source and draft wording
   in the centre, and AI findings on the right. Smaller screens stack these panels.
4. Filter by severity, product, finding category, requirement and review status. Source
   buttons open exact extracted-text locations or the actual in-house reference snapshot.
5. Accept, edit, reject, request clarification, comment or mark resolved. Every action
   needs a reason and persists reviewer, role, time, baseline, finding version, and
   before/after state. Accept/edit actions create reviewed drafts; they never replace a BRD.
6. Reanalyse a requirement or the BRD after clarification. Targeted reanalysis still returns
   the complete baseline, preserving other blockers. Identical requests are idempotent;
   unchanged proposals retain their prior review disposition and origin review ID.
7. Record human BA sign-off when findings are resolved/rejected. A blocked analysis or
   unresolved material issue cannot be bypassed with a resolve button. Correct the BRD
   and reanalyse critical calculation/compliance issues.
8. Use **Your decision** to add feedback. If review evidence is missing, add it in the
   form shown there. The BA selects **Send for business approval**; the business approver
   selects **Approve BRD** or **Request changes**. A short note explains the next handoff
   or what is blocking approval. BA sign-off does not automatically advance the lifecycle
   or grant stakeholder/business approval.

The original Requirements-stage BA/alignment checks are available under a disclosure.
New BRD versions reset the existing lifecycle, flag prior review runs as impacted, and
require a new review/sign-off. Analysis after business approval requires a revised baseline.

## Automatically populated supporting records

A completed AI review creates draft requirement records with acceptance criteria and
verified BRD references. Each record identifies the AI review and source baseline. The
history records the actual drafting event as an AI action; human sign-off, evidence and
approval are never generated automatically. Owners and estimates remain for human input.

These source-linked records are retained behind the scenes for traceability. The BA page
provides **Business documents** downloads instead of a supporting-record workbench:

- Business review (Markdown): scope, deliverables, expected benefits and sign-off.
- Review metrics (CSV): actual saved assessment counts and sign-off state.
- Saved BRD (text): the extracted baseline, not a reconstruction of the original upload.
- Review history (JSON): actual decisions, assessments, source requirements and audit trail.
- All business documents (ZIP).

Reanalysis preserves human edits and existing records. Revised baselines retain earlier
records as impacted history. Failed, cancelled and stale analyses do not create drafts.

## BA sign-off to Backlog

Review the AI findings, resolve or reject them with reasons, then open **Your decision**
and select **Sign off BRD for story drafting**. The existing server sign-off checks still
block unresolved findings, missing business decisions and unsupported readiness. A signed
current BRD enables **Create user stories in Backlog**. The BA can author draft stories
with acceptance criteria and links to the current source requirements. The Backlog action
preselects those source links; it does not generate or approve stories automatically.
The story editor opens directly on Backlog. Saving closes the editor and adds the story
to **Created user stories** below it. Review/edit, version updates and reload persistence
stay on Backlog; the former QA story-design shortcut has been removed.

The server enforces the gate for BA story writes. A revised BRD, new analysis without
sign-off, or relevant requirements rework closes it again. BA authors draft/blocked
stories; product owners retain estimation, assignment, sprint planning and readiness.
Business approval and the accountable lifecycle handoffs remain separate. Drafting a
story never advances the lifecycle or grants business, release or deployment approval.

Downloads use the authenticated project membership check, attachment responses and
no-store caching. Metrics report recorded facts, not fabricated financial benefits,
coverage percentages or completeness claims.

## In-house domain grounding

The review reuses `BusinessAnalystAgent.review_knowledge()`; it does not introduce another
knowledge store or fetch unapproved web material. Sources include:

- Effective approved sources in the configured requirements baseline.
- Applicable approved rules from `workspace/auto-finance-domain.toml`, when enabled.
- The existing scoped UK auto-finance reference library and profile knowledge.

Each run retains the actual source content, authority, version and knowledge fingerprint.
Changing the knowledge fingerprint requires reanalysis before sign-off. Reference-only
guides are never treated as approved lender policy.

The repository-owned agent instructions cover UK finance requirements quality, PCP/HP/
leasing distinctions, GMFV/residual dependencies, calculation methods and rounding gaps,
maintenance inclusion, API validation, conflicts/duplicates, NFRs and regulatory questions.
LP/PFL/BFL contractual meanings, maintenance codes and brand-specific rules require approved
definitions. Missing regulated-status/jurisdiction questions are compliance review flags,
never definitive legal conclusions. Suggested formulas, policies or API fields are not
silently added to the BRD or approved quotation payload.

## Contracts and enforcement

`app/ba_review_models.py` defines strict schema version 1.0. The provider returns extracted
requirements, classified findings, dependencies, questions and calculation-analysis drafts.
The backend verifies quotations against real BRD lines and authorised knowledge snapshots,
validates cross-references, requires two distinct references for conflicts/duplicates,
rejects AI approval values, derives conservative readiness and assigns stable content-based IDs.
Server-owned review metadata and handoff information identify the document, version and run.
No numerical readiness or compliance score is shown.

Authenticated project members can read reviews. Only human BA/admin/test-lead sessions can
start/cancel analysis, decide findings or sign off. Project membership is checked independently
of role. Optimistic run/finding revisions prevent stale edits. Superseded runs are read-only.
All review changes also increment the lifecycle revision and append lifecycle audit events.

If an inline review exists, BA-validation completion, positive stakeholder approval and
deployment require its current-baseline human sign-off. Legacy projects retain their prior
manual evidence workflow until an inline review is initiated. Existing blocked source
assessments continue to block approval; the new UI cannot erase them.

Endpoints live under `/api/sdlc/projects/{project}/ba-reviews`: list/start, read a run,
`/{run}/decisions`, `/{run}/signoff`, and `/{run}/cancel`. SQLite schema changes are additive.
No external messaging, new frontend framework or model-policy override is introduced.

## Honest limits

- Existing ingestion retains extracted text and table text, not dependable original PDF
  pages or Word layout metadata. This version links exact extracted lines and reports
  page/layout information as unavailable. It does not invent page numbers.
- Background jobs use the existing web process with durable queued/running/terminal state,
  a 30-minute execution bound and a 35-minute stale-job expiry. A restart does not resume
  a provider call; expired jobs become retryable failures. Cross-process cancellation
  prevents result publication; immediate provider interruption is local to the worker.
- Reanalysis is source/version-aware and idempotent; it is not a semantic diff engine or
  an independent executable finance-calculation verifier. Calculation entries identify
  approved methods, evidence and decisions for BA review. No generic formula proves accuracy.
- Provider access and generation time affect availability. Synthetic-provider acceptance
  tests prove UI/API/persistence controls, not live-model analytical quality.
- No regulatory, business, release or deployment approval is granted by this implementation.

## Suggestion selection

Each suggestion occupies one full-width collapsible tile. Tiles start closed, showing the
suggestion and requested change/clarification. Expanding a tile reveals its required feedback
reason and Request feedback, Accept suggestion and Decline suggestion actions. Feedback
requests use the existing clarification decision contract. Decline uses the existing rejection decision contract. Each submission
includes that finding's ID/version and the current review revision; reason drafts remain
bound to their finding across selection changes. The selected row expands its BRD comparison,
proposed wording, saved feedback and additional review actions. Accepted proposals remain
drafts, and the existing server sign-off checks still apply.

## Updated BRD and automatic revalidation

After every finding has a human decision, Create updated BRD & revalidate saves a new
requirements-input version. Accepted/edited wording replaces a single unique source quote
when its span is unambiguous; otherwise it appears as a referenced, superseding BA amendment.
Declined proposals are excluded. Requested feedback remains an explicitly unapproved question,
with its BA comment, and blocks sign-off until resolved in a revised Requirements source.
Existing open requests are retained across generated revisions.

The server uses the stored BRD and decisions, validates the review revision again inside the
source-save transaction, and retains prior documents and decisions. The selected provider and
request context are preserved. Original upload receipts are not reused for edited text.

The new baseline automatically runs the business assessment, approved-source alignment and a
fresh inline BA analysis. Status appears in AI analysis progress; Download updated BRD provides
the new text before sign-off. Revalidation does not approve the source. Failures leave the new
version downloadable and allow retry through AI analysis. Blocked business/alignment outcomes
and unanswered requests prevent sign-off. Prior approvals and downstream drafts require review
against the new baseline. The Requirements editor is updated to the server-saved text.

POST `/api/sdlc/projects/{project}/ba-reviews/{review}/revised-brd` accepts only the current
review revision from an authenticated BA, test lead or administrator. The executable scenarios
in `automation/Features/UpdatedBRD.feature` cover pending decisions, accept/edit/decline/feedback,
original-version retention, fresh assessments, stale updates and open-question sign-off guards.
The isolated acceptance harness substitutes provider outputs and executes these through actual
ReqnRoll alongside the existing scenarios; it does not demonstrate live model quality.

## AI analysis progress

A shared panel at the top of every BA review section shows the current-baseline AI suggestions
analysis status: not started, submitting, queued, running, completed, failed or cancelled.
It displays the server progress message and update timestamp; active runs use an indeterminate
indicator and existing polling rather than an estimated percentage. Status-fetch errors show
an unavailable state, the last known state when available, and a retry action. Reopening the
page reloads the saved review; a stale-baseline run does not count as current analysis.

## Overall BA decision and business approval

Your decision uses one overall BA comment for either Request changes or Sign off for story
drafting. Rework uses the existing human lifecycle transition with the current revision;
sign-off uses the existing source-bound review checks. Individual suggestion decisions remain
in AI suggestions. Manual evidence entry appears only for missing required evidence.

After effective sign-off, the page shows the recorded comment, Backlog link and Business
documents navigation. Before sign-off, document navigation and its BA workspace section stay
hidden; direct section URLs show Your decision. Invalidated sign-off hides the section again. Remaining
lifecycle routing is available separately under Business approval routing and reuses that
comment. At the stakeholder approval stage, the accountable approver sees a separate business
approval form. BA sign-off does not grant business approval or bypass lifecycle evidence.

## Optional feedback-loop validation

The earlier Requirements-stage assessment stays available as read-only evidence. On BA review,
“Revalidate saved BRD” is enabled only when the latest inline AI review belongs to the current
project and BRD baseline, has completed, and contains suggestions. Queued, running, failed,
empty or stale reviews do not enable it. The click handler applies the same UI gate.
This recheck runs the existing BA and source-alignment validations against the saved BRD;
it does not merge proposed wording or grant approval.

## Repeatable verification

Run the focused Python regressions and browser regressions described in the implementation
record. Run `PYTHONPATH=. .venv/bin/python tests/support/run_ba_review_acceptance.py` for an
isolated authenticated app, real SQLite persistence, browser review flow and executable C#
ReqnRoll scenarios. Only provider output is replaced in this test harness; production code
contains no fixtures or mock findings. The runner uses temporary credentials/data and
preserves the original BA-input and lifecycle scenarios alongside the new pack.

For an opt-in live Codex check with synthetic source material, run
`PYTHONPATH=. .venv/bin/python tests/support/check_inline_ba_provider.py`. This checks
actual model output through the same schema and source-validation contract. The recorded
live run returned BLOCKED readiness and calculation/dependency findings for a PCP BRD with
missing GMFV and calculation decisions; it is one evaluation, not exhaustive model validation.

Synthetic acceptance documents are in `automation/Input/InlineBAReview.Json`. They cover
the ten requested automotive-finance cases, all review actions, stale decisions, source
updates, cancellation, permissions and project isolation. They are not lender policies.
