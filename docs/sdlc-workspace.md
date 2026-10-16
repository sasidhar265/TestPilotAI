# Agent-led SDLC delivery

The sidebar has one **SDLC workspace** group. Planning and BA, Design and Development,
Testing (including execution reports and coverage), and Release and Operations are
its stage sections. Supporting pages use the same hierarchy.

Open **Requirements** (`/`) first. Select or create a project, enter requirements or
attach a BRD, add business rules and constraints, choose the provider and delivery
target, then select **Save and start SDLC**. Requirements are saved as an immutable
`requirements-input` version before any stage agent runs. **SDLC workflow** (`/sdlc`)
shows stage ownership, gate results, execution evidence and recovery actions.

Downstream documents are read-only agent outputs. Reviews remain version-specific.
Change scope in Requirements and start a new run; a run cannot resume against changed
requirements. The API accepts only `requirements_version` and `target` for launching,
resolves all business inputs from the saved project baseline, and rejects independently
supplied briefs and manual downstream artifact writes.

## Executable stage ownership

| Stage agent         | Work performed                                                                                                                        | Handoff or gate                                                                                                   |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Planning            | Scope, outcomes, risks, milestones and a task dependency graph                                                                        | Typed planning artifact; unique task IDs; acyclic dependencies; no unresolved blockers                            |
| Business Analysis   | Existing requirements validation, BA assessment and source-grounded story generation                                                  | Actual BA/requirements reports and stories; unresolved questions stop delivery                                    |
| Architecture        | Components, interfaces, data models, security and design decisions                                                                    | Every story ID must be covered by architecture tasks                                                              |
| Development         | Source generation in an isolated checkout, syntax validation, independent code review, build and one repair attempt                   | Complete source files, manifest, review, build output and candidate tree revision                                 |
| Quality Engineering | Existing scenarios and test-generation pipeline, Quality Gate, complete C# automation pack, preview deployment and ReqnRoll execution | Actual TRX outcomes for every generated scenario/outline row against a revision-verified preview                  |
| Release             | Evidence-based release plan, staging deployment and verification, optional PROD promotion                                             | Matching candidate revision, deployment receipts, healthy deployed revision; rollback on failed PROD verification |
| Operations          | Verify the released revision and produce runbooks and operational handover                                                            | Time-stamped health evidence, support ownership and maintenance tasks                                             |

Agents use the existing `ArtifactGenerationRunner`, provider routing and profile
knowledge. Codex calls, retries and repairs use `gpt-6-astra`; Copilot uses
`claude-haiku-4.5`. Explicit provider selections remain on that provider. Only the
existing `auto-fallback` route permits provider switching. Agent policies are in
`.github/agents/sdlc-*.agent.md`; existing BA and testing policies remain authoritative.
All seven stage descriptors appear in `/api/agents` and `/api/sdlc/agents`.

The saved Requirements request carries the description, constraints, business rules,
finance context and uploaded-document receipt into every stage. Every generated
artifact links to this exact source version and preceding stage outputs.
The existing auto-finance profile and approved quotation payload remain authoritative
where applicable. Agents stop when business decisions or contracts are missing.

## Delivery targets

- **Design:** Planning → BA → Architecture.
- **Tested:** adds implementation, independent review, successful build and actual BDD execution.
- **Staging:** adds staging deployment, revision verification and operational handover.
- **Production:** verifies staging, promotes the tested candidate to PROD, verifies PROD
  and performs operational handover. Failed PROD health invokes the configured rollback
  hook and verifies the previous revision before marking the run blocked.

Agent validation is recorded separately from human artifact approval. Generated BA
reports retain `business_approval: not_granted`; the runtime does not fabricate reviewer
acceptance. Existing test-suite review and acceptance controls remain available.

## Repository and environment configuration

Commands and deployment endpoints are server-owned configuration, never generated
shell text or browser-supplied commands. Command values are JSON argument arrays,
executed directly without a shell. Configure these through the deployment environment
or the existing settings mechanism:

| Setting                        | Purpose                                                        |
| ------------------------------ | -------------------------------------------------------------- |
| `SDLC_REPOSITORY_PATH`         | Trusted local Git repository with a committed HEAD             |
| `SDLC_GREENFIELD_ENABLED`      | Allow a new empty scaffold when no repository is connected     |
| `SDLC_BUILD_COMMAND`           | Build/compile the candidate using its isolated checkout as cwd |
| `SDLC_PREVIEW_COMMAND`         | Publish the candidate into an isolated test environment        |
| `SDLC_PREVIEW_BASE_URL`        | API/browser base URL for the generated BDD pack                |
| `SDLC_PREVIEW_HEALTH_URL`      | Preview endpoint reporting the deployed candidate revision     |
| `SDLC_STAGING_COMMAND`         | Publish the tested candidate into staging                      |
| `SDLC_STAGING_HEALTH_URL`      | Staging endpoint reporting the deployed candidate revision     |
| `SDLC_PRODUCTION_ENABLED`      | Explicit server policy enabling PROD promotion                 |
| `SDLC_PRODUCTION_COMMAND`      | Publish the staging-verified candidate into PROD               |
| `SDLC_PRODUCTION_HEALTH_URL`   | PROD endpoint reporting the currently deployed revision        |
| `SDLC_ROLLBACK_COMMAND`        | Restore the previous revision after failed PROD verification   |
| `SDLC_COMMAND_TIMEOUT_SECONDS` | Per-command timeout; default 900 seconds                       |
| `SDLC_MAX_ACTIVE_RUNS`         | Concurrent delivery workers per server process; default 2      |

For example, a configured command can be `["python3","/opt/delivery/build.py"]`.
Provide trusted scripts that implement the actual project/platform operations. The
application does not infer a deployment account, target stack, environment or credentials.
A greenfield mission still needs a build command and subsequent environment connections.

Existing repositories are exported from committed HEAD into a project/run-specific
workspace; the original checkout is not modified. Generated files cannot escape that
workspace, follow symlinks or write into Git/credential directories. Source archives
exclude environment files. Every implementation and build is associated with a Git tree
revision; this is a content revision, not a newly published upstream Git commit.
Deploy hooks publish/build from the isolated source workspace. Remote push/PR behavior,
if required by the deployment platform, belongs in its configured trusted hook.

## Deployment hook contract

Each deployment hook receives:

```text
SDLC_WORKSPACE       absolute path to the isolated candidate source
SDLC_REVISION        candidate Git tree revision (previous revision for rollback)
SDLC_ENVIRONMENT     preview, staging, production, or rollback
SDLC_RECEIPT_PATH    absolute path where the hook must write its receipt
SDLC_DEPLOYMENT_KEY  stable run/environment key for platform idempotency
```

The command must exit successfully and write JSON at `SDLC_RECEIPT_PATH`:

```json
{
  "environment": "production",
  "revision": "the exact SDLC_REVISION value",
  "deployment_id": "the actual platform deployment identifier",
  "previous_revision": "the previous healthy revision for rollback"
}
```

`previous_revision` is needed for PROD rollback. Do not write credentials into receipts.
Only the documented receipt fields enter the stage artifact. A successful deployment
command alone is insufficient: health must return a successful response with the exact
revision in the `X-SDLC-Revision` header or JSON `revision` field. Five bounded probes
allow brief startup delay. A successful HTTP response for a different revision fails. Preview is checked again after
BDD execution. Shared preview and promotion steps are serialized within the server
process; multi-worker platform hooks must provide environment isolation/serialization.

Receipt reuse on resume never re-executes an already recorded deployment. Health is
verified again. Configure platform hooks to honour `SDLC_DEPLOYMENT_KEY` for the crash
window between an external deployment and receipt creation. Inspect receipts and the
platform when a worker is interrupted; do not assume an interrupted command had no effect.

Build and test subprocesses receive a limited environment. Deployment hooks receive
server deployment credentials; credentials do not enter agent prompts. Stored command
output is bounded and redacted. Delivery bundles contain current candidate source and
pack source, excluding Git metadata, credential files, dependencies and raw runtime reports.
Actual structured test results remain available in the delivery evidence.

## Persistence, recovery and BA/testing integration

`sdlc.db` beside the configured organizational-memory file stores account-scoped projects,
immutable artifact revisions, version-specific reviews, runs and ordered agent events.
AI knowledge reuse can remain disabled. Back up this database and `sdlc-workspaces` together.
A project has one active delivery at a time. Lifecycle artifact editing is locked while a
delivery owns its baseline; stop the run before changing the source. Worker heartbeats
identify interrupted runs.

**Resume from failed gate** reuses completed stage handoffs and retries the blocked or
failed stage on the same mission/provider. If an upstream artifact has changed, start a
new reconciled mission instead of promoting stale evidence. Development retries restore
the trusted baseline before applying newly reviewed files. Prior candidate/pack attempts
remain in the run workspace for investigation.

**Stop delivery** cancels generation/build/test work and stops between promotion steps.
An in-progress deployment hook is allowed to finish so its result can be recorded; a
requested stop is checked before the next promotion. Rollback recovery takes precedence
when the released candidate is unhealthy. Stopping does not remove completed artifacts.

A successful Quality Engineering stage also saves a testing-workspace handoff containing
BA reports, stories, scenarios, cases, validation, automation files and actual execution
outcomes. Use the Testing artifact's **Restore testing workspace** action to inspect these
in the existing quality UI. Human approvals are not fabricated during this restoration.
Manual testing and the previous requirements/story/scenario/test/execution flows remain
available independently. Saved testing workspace snapshots are working drafts; existing
STLC baselines retain their separate approval and execution-evidence semantics.

Administrators and test leads can run full delivery missions and approve artifacts.
Business analysts can run design-only missions, save BA/design records and stop/resume
their design-only work. Testers retain their previous permissions and can save Testing
records and workflow drafts. Existing role checks remain enforced server-side.

## Verification and practical limits

The repository ReqnRoll API pack has executable SDLC bindings, request builders, shared
HttpClient transport and `Input/SDLC.Json`. Its scenarios check agent/model discovery,
version-specific reviews, stale writes, invalid mission boundaries and unknown run
operations against a running app. These are application API checks, not evidence that
a product generated by an SDLC mission passed its tests or reached PROD.

Coordinator and tool tests use isolated repositories and simulated specialist/deployment
fixtures. Browser checks verify the cockpit, mission submission, failed-gate display,
project recovery and existing BA/testing navigation. Real model generation and a complete
product delivery require configured providers, repository/build tools, a preview target,
staging/PROD hooks and health endpoints. Operations verifies current health and generates
runbooks; ongoing alert delivery and incident monitoring require the platform's monitoring
integration.
