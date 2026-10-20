# Role permissions

Existing account roles are retained; no accounts or identity data are migrated. `app/roles.py` provides labels/capabilities, `app/role_access.py` authorises routes and `can_act` in the shared lifecycle policy authorises transitions. Project membership is also required.

| Account role | Accountable lifecycle stages |
| --- | --- |
| Business stakeholder (`business_stakeholder`) | Stakeholder approval, Uat |
| Product owner / Scrum master (`product_owner`) | Backlog generation, Backlog refinement, Prioritisation estimation, Sprint planning, Uat |
| Developer (`developer`) | Development, Code review, Ci checks, Defect resolution |
| Release manager / DevOps (`release_manager`) | Ci checks, Release readiness, Release approval, Staging validation, Production approval, Production deployment, Post deployment verification, Release closure, Closed |
| Business analyst (`ba`) | Brd upload, Requirements analysis, Ba validation, Clarification |
| Functional tester (`functional_tester`) | Qa testing, Qa retesting |
| Automation tester (`automation_tester`) | Qa testing, Qa retesting |
| Non-functional tester (`non_functional_tester`) | Testing work within existing capabilities; no separate sign-off grant |
| Test lead (`test_lead`) | Qa testing, Qa retesting, Qa signoff |
| Admin (`admin`) | All stages, with normal evidence and human-session checks |

## Approval and record responsibilities

Business Analyst maintains source-grounded requirements and BA evidence. After current-baseline human BA sign-off, the BA can create linked draft user stories in Backlog. BA drafting does not grant stakeholder approval or product-owner planning authority. Business Stakeholder approves or requests clarification. Product Owner refines and plans the backlog. Developer maintains implementation/reference status and resolves defects. Existing functional/automation tester roles represent QA engineers; Test Lead owns QA sign-off. Release Manager owns release and deployment gates. Administrators manage accounts and project owners manage membership.

Record edits/comments/suggestion decisions use existing work-item permissions. Selecting a sidebar phase grants no new authority. Positive stakeholder approval is blocked by current-source server review blockers; rejection requires actionable comments and returns work to clarification.
