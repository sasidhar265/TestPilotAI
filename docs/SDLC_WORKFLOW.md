# Governed SDLC workflow

`app/lifecycle_workflow.py` is the server-owned configurable definition. `GET
/api/sdlc/projects/{id}/lifecycle` supplies its labels, accountable roles, entry/exit
criteria, allowed successors, rejection targets, current revision, missing evidence
and audit. The browser consumes this definition. Agent stages are execution phases,
not the authoritative human project state.

BRD save → requirements analysis → BA validation → stakeholder approval → backlog
generation → refinement → prioritisation/estimation → sprint planning → development
→ code review → CI → QA → QA sign-off → UAT → release readiness → release approval
→ staging validation → production approval → deployment → verification → closure.
BA rejection returns to clarification, then analysis. QA failure returns to defect
resolution, then retesting and sign-off. Release rejection returns to readiness.
The full transition and evidence matrix is exposed by the definition endpoint.

Every transition requires an authenticated human session, the accountable role (or
administrator), the expected lifecycle revision and nonblank comments. Service bearer
tokens and unauthenticated local-development identities cannot make lifecycle decisions.
Evidence must pass for the current stage and requirements baseline. Evidence submissions
are explicitly human attestations, not verified integration receipts. An AI run cannot
write business decisions through this API.

Approvals retain identity, role, decision, time, source version, captured artifact
versions, project/work item and audit event. Concurrent stale decisions fail with 409.
Rejection preserves history and starts a fresh evidence epoch. Updating the requirements
source resets analysis and marks older evidence impacted. Editing a requirement work item
also resets analysis; dependent work items retain the linked source versions and show
transitive impact until revalidated. Historical reviews remain historical evidence.

Versioned work items cover requirements, epics, stories, tests, defects, releases and
documentation. Allowed link types and status transitions live in
`services/project_work_items.py`. New records start in draft. Ready stories require
acceptance criteria and estimates; development requires an assigned project developer.
Developers cannot redefine PO-owned story scope or close defects; QA closes after retest.
Unclosed defects block QA sign-off, UAT and release approvals.

Deployment commands require a governed run and the matching human release state.
The command boundary checks version-specific approvals, the implemented candidate revision
and passing test execution for that revision. Existing server production-disable policy,
receipt validation, rollback and source-version checks remain enforced. No production
commands were executed during this implementation.

Project records persist in the existing SDLC SQLite database. New tables are additive;
the existing account migration preserves accounts and hashes while widening role choices
and revoking stale sessions. Existing projects initialize in BRD upload rather than
inferring approvals from old agent runs. Existing STLC records are not silently reassigned.

For an end-to-end agent delivery, choose the intended target at the initial Requirements
save. The same durable run blocks at human handoffs and resumes after the accountable
owner completes the gate. Use Resume rather than saving an unchanged requirements source
as a new version: a new source version deliberately requires fresh review. A completed
shorter-target run does not itself authorise a later production promotion.

## Stage policy reference

Generated from app/lifecycle_workflow.py.

| Stage                        | Accountable roles                               | Required evidence                | Next                         | Rejection / rework |
| ---------------------------- | ----------------------------------------------- | -------------------------------- | ---------------------------- | ------------------ |
| brd_upload                   | ba                                              | brd                              | requirements_analysis        | —                  |
| requirements_analysis        | ba                                              | analysis                         | ba_validation                | brd_upload         |
| ba_validation                | ba                                              | ba_validation                    | stakeholder_approval         | clarification      |
| clarification                | ba                                              | clarification                    | requirements_analysis        | brd_upload         |
| stakeholder_approval         | business_stakeholder                            | Authenticated human approval     | backlog_generation           | clarification      |
| backlog_generation           | product_owner                                   | backlog                          | backlog_refinement           | ba_validation      |
| backlog_refinement           | product_owner                                   | refinement                       | prioritisation_estimation    | backlog_generation |
| prioritisation_estimation    | product_owner                                   | estimation                       | sprint_planning              | backlog_refinement |
| sprint_planning              | product_owner                                   | assignment                       | development                  | backlog_refinement |
| development                  | developer                                       | implementation                   | code_review                  | backlog_refinement |
| code_review                  | developer                                       | pull_request, code_review        | ci_checks                    | development        |
| ci_checks                    | developer, release_manager                      | build                            | qa_testing                   | development        |
| qa_testing                   | functional_tester, automation_tester, test_lead | test_execution                   | qa_signoff                   | defect_resolution  |
| defect_resolution            | developer                                       | defect_fix                       | qa_retesting                 | development        |
| qa_retesting                 | functional_tester, automation_tester, test_lead | retest                           | qa_signoff                   | defect_resolution  |
| qa_signoff                   | test_lead                                       | Authenticated human approval     | uat                          | defect_resolution  |
| uat                          | business_stakeholder, product_owner             | uat                              | release_readiness            | defect_resolution  |
| release_readiness            | release_manager                                 | release_checklist, rollback_plan | release_approval             | development        |
| release_approval             | release_manager                                 | Authenticated human approval     | staging_validation           | release_readiness  |
| staging_validation           | release_manager                                 | staging                          | production_approval          | release_readiness  |
| production_approval          | release_manager                                 | Authenticated human approval     | production_deployment        | release_readiness  |
| production_deployment        | release_manager                                 | deployment                       | post_deployment_verification | release_readiness  |
| post_deployment_verification | release_manager                                 | verification                     | release_closure              | release_readiness  |
| release_closure              | release_manager                                 | release_notes                    | closed                       | release_readiness  |
| closed                       | release_manager                                 | Terminal state                   | —                            | —                  |

## Sequential workspace presentation

`PHASES` in app/lifecycle_workflow.py groups the existing business states into eight
ordered workspace steps. Lifecycle snapshots expose `phase` and `phases`; agent catalogue
responses also expose the workflow presentation metadata so a new project can show the
sequence before artifacts exist. Each phase lists its substages, relevant record types,
agent artifact categories and existing workspace links. All 25 business states belong
to exactly one phase, verified by unit and ReqnRoll checks.

Selecting a phase is review navigation. It does not save evidence, approve an artifact,
advance a stage or start an agent. Future-step previews are read-only; stage actions are
shown in the current phase, with the same backend role and evidence enforcement as before.
Clarification and defect/retest branches remain part of the original state machine.
Earlier steps are labelled "Earlier step", not automatically claimed as completed.


### Sequential entry (2026-10-16)

The signed-in landing page is the SDLC workflow. Select/create a project above the
steps, enter or attach the BRD in Step 1, save a requirements version, then complete
the current human-owned stage. “View next step” previews the next stage and never
advances backend state. Source save and optional AI execution are separate actions.
Legacy explicit testing-tool links remain supported. Guest preview retains its source workspace.
