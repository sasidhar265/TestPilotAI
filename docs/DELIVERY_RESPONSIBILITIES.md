# Governed delivery workflow

The SDLC workspace follows the BRD-to-production lifecycle. Each phase displays the
AI draft responsibility, accountable human responsibility and expected handoff artifacts.
The backend policy in `app/lifecycle_workflow.py` supplies these contracts to both the
workspace and the agent instructions, alongside the existing enforced model policy.

| Workspace phase | AI assistance | Accountable human handoff |
| --- | --- | --- |
| Requirements | Extract PDF/Word requirements; identify gaps, ambiguities, conflicts and dependencies | BA checks correctness against the versioned source |
| BA review & approval | Recommend corrections and clarification questions | BA validates; business stakeholder signs off the baseline |
| Backlog | Draft epics, stories, acceptance criteria, priorities and estimates | PO and team refine, prioritise, estimate and plan assignments |
| Development | Assist with implementation, unit tests, design notes and review findings | Developer picks an approved story, implements, opens a PR and reviews |
| Quality assurance | Draft test cases and API/UI automation; summarise actual evidence | QA executes, investigates, manages defects, retests and signs off |
| Release readiness | Summarise UAT, regression, security evidence, risks and rollback readiness | Business accepts UAT; release manager approves progression |
| Deployment | Summarise configured CI/CD receipts and verification | Release manager validates staging, approves production and verifies operations |
| Closure | Draft release notes, handover and documentation | Artifact owners validate and publish; release manager closes |

Navigation reviews a phase without advancing the project. Authenticated human transitions,
role checks, current-baseline evidence and attributable decisions remain server-owned.
A source change returns work to requirements analysis and flags downstream evidence for
review. Defect rework requires retesting; developers cannot close defects in place of QA.

Documentation accompanies every phase: requirements traceability, design notes, test
evidence, release notes and audit history. Draft generation does not establish approval or
publication. The documentation link opens the existing project artifact/version ledger.

Project creation and selection happen after sign-in on the dedicated project-selection page;
the Requirements view retains optional delivery settings. See `PROJECT_SELECTION.md`.
It does not show the manual lifecycle work-item and evidence section. BA review & approval
shows saved BA results and owns the human review forms, including the initial analysis
handoff. Server stage, evidence and role checks continue to govern those actions.
BA review shows an explicit clarification empty state when the report contains no open
questions; the BA still checks completeness against the saved BRD.

## Execution boundaries

These contracts describe responsibility and handoff artifacts. They do not provision
external tools. Actual AI generation requires access to the selected provider. Builds,
staging, production deployment, health verification and rollback require their configured
repository, commands and environment URLs. Missing integrations remain blockers. Human
attestations are labelled as such and do not independently verify a referenced artifact.

Repository lifecycle BDD verifies governance with fixture attestations; it does not prove
that a generated automation pack passes in its target environment or that production has
been deployed. Continuous monitoring also requires an operational integration.
