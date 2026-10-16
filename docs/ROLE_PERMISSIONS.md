# Roles and permissions

Existing sessions and account administration remain authoritative. Global account role
plus explicit project membership is required; membership never changes role permissions.
The project owner adds existing enabled accounts through the project team form. Shared
project access does not expose other owners' projects. Only the owner can invite members.

| Role                                  | Accountable lifecycle work                                                                                                |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| ba                                    | Upload, analysis, BA validation and clarification; requirement records                                                    |
| business_stakeholder                  | Business approval and UAT                                                                                                 |
| product_owner                         | Backlog generation/refinement, estimation, sprint assignment, UAT                                                         |
| developer                             | Development, review, CI, defect resolution; existing story scope is PO-owned                                              |
| functional_tester / automation_tester | QA testing, retesting, test and defect records; existing testing restrictions retained                                    |
| non_functional_tester                 | Existing nonfunctional tools; no business/release approvals                                                               |
| test_lead                             | QA sign-off, testing and defects; existing test-lead capabilities retained                                                |
| release_manager                       | CI, release readiness/approval, staging, production approval, deployment, verification and closure; governed run recovery |
| admin                                 | Account management and stage-owner override; still requires signed human session, evidence and release controls           |

New role names use the existing Role contract, account form and safe account-table migration.
Legacy testing role names remain valid. Lifecycle APIs enforce project access and role
rules regardless of browser visibility. Service tokens remain privileged integrations but
cannot attest evidence or submit human lifecycle decisions. Legacy artifact reviews are
review notes and cannot substitute for any lifecycle approval.


The SDLC landing page and persistent project selector are shared navigation. Moving
the original requirements editor into Step 1 does not change its capabilities or
backend authorization. Specialist links continue to use server-issued role visibility;
previewing a numbered step grants no transition permission.

### Inline review and contextual assistance

All enabled project members may read scoped record history and post human-session
clarification comments against the version they reviewed. Suggestion use/dismiss requires
an editing role for that record kind, a current item version and a real current-baseline
agent task source. Stakeholders do not acquire BA editing rights through discussions.
Developers receive only status/reference edit fields for stories; the backend retains
PO ownership of scope, priority, estimation, assignment and sprint changes. Global shared
rule publication permissions are unchanged by project-scoped BRD saving. Requirement
amendments retain the existing automatic review/approval invalidation rules.
