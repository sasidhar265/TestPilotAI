# SDLC workflow

The existing `app/lifecycle_workflow.py` is the authoritative policy. The API returns its stages/phases; UI navigation previews a stage and never grants approval. All transitions require project access, accountable role, a current lifecycle revision, version-bound evidence and an authenticated human decision.

| Stage | Owner | Exit evidence | Next | Rejection / rework | Human approval |
| --- | --- | --- | --- | --- | --- |
| Brd upload | Business analyst | brd | requirements_analysis | None | No approval grant |
| Requirements analysis | Business analyst | analysis | ba_validation | brd_upload | No approval grant |
| Ba validation | Business analyst | ba_validation | stakeholder_approval | clarification | No approval grant |
| Clarification | Business analyst | clarification | requirements_analysis | brd_upload | No approval grant |
| Stakeholder approval | Business stakeholder | Human decision | backlog_generation | clarification | Required |
| Backlog generation | Product owner / Scrum master | backlog | backlog_refinement | ba_validation | No approval grant |
| Backlog refinement | Product owner / Scrum master | refinement | prioritisation_estimation | backlog_generation | No approval grant |
| Prioritisation estimation | Product owner / Scrum master | estimation | sprint_planning | backlog_refinement | No approval grant |
| Sprint planning | Product owner / Scrum master | assignment | development | backlog_refinement | No approval grant |
| Development | Developer | implementation | code_review | backlog_refinement | No approval grant |
| Code review | Developer | pull_request, code_review | ci_checks | development | No approval grant |
| Ci checks | Developer, Release manager / DevOps | build | qa_testing | development | No approval grant |
| Qa testing | Functional tester, Automation tester, Test lead | test_execution | qa_signoff | defect_resolution | No approval grant |
| Defect resolution | Developer | defect_fix | qa_retesting | development | No approval grant |
| Qa retesting | Functional tester, Automation tester, Test lead | retest | qa_signoff | defect_resolution | No approval grant |
| Qa signoff | Test lead | Human decision | uat | defect_resolution | Required |
| Uat | Business stakeholder, Product owner / Scrum master | uat | release_readiness | defect_resolution | No approval grant |
| Release readiness | Release manager / DevOps | release_checklist, rollback_plan | release_approval | development | No approval grant |
| Release approval | Release manager / DevOps | Human decision | staging_validation | release_readiness | Required |
| Staging validation | Release manager / DevOps | staging | production_approval | release_readiness | No approval grant |
| Production approval | Release manager / DevOps | Human decision | production_deployment | release_readiness | Required |
| Production deployment | Release manager / DevOps | deployment | post_deployment_verification | release_readiness | No approval grant |
| Post deployment verification | Release manager / DevOps | verification | release_closure | release_readiness | No approval grant |
| Release closure | Release manager / DevOps | release_notes | closed | release_readiness | No approval grant |
| Closed | Release manager / DevOps | Human decision | Closed | None | No approval grant |

## Shared rules

- Administrator can act on stages but still needs a human session and all evidence; AI/service sessions cannot approve.
- Business stakeholder decisions capture actor, role, comment, timestamp, BRD baseline, artifact versions and work-item versions in the append-only audit history.
- Changed BRD/requirements reopen analysis and invalidate downstream evidence/approval applicability. Earlier decisions remain visible as historical decisions.
- Blocked matching server alignment or BA/domain clarification reports prevent positive business approval. Browser workflow drafts never become server assessment evidence.
- Current-baseline manual BA evidence remains supported for existing projects; missing external AI credentials are never represented as a completed AI assessment.
- QA/release gates reject unresolved defects. Deployment requires current-baseline human approvals and the exact implemented/tested revision.
- Documentation records and traceability links are available in every relevant phase; Documents and version history browses immutable source artifacts.
- No production deployment was performed or authorised by this implementation task.

## Implementation boundaries

Workflow policy is centralised in Python rather than editable browser state. Changing policy requires a reviewed application change. Live repository/CI/provider/deployment dependencies remain configuration-driven; tests with synthetic evidence do not certify live integrations.
