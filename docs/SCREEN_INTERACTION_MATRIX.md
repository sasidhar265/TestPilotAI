# Screen interaction matrix

| Workspace | Interaction | Authoritative API / persistence | Permission / feedback |
| --- | --- | --- | --- |
| SDLC | Numbered phase, current owner, blocked evidence, human decision | lifecycle, evidence, transitions | Existing role/session/revision gates |
| Requirements / business approval | Search/select requirement, edit title/description/criteria inline; comment; inspect versions | work-items; item detail and annotation endpoints | BA edits; invited stakeholder reviews/comments and approves current project version through human gate |
| Backlog | Inline scope, priority, estimate, sprint, assignment and dependencies | Same work-items API | PO governs scope; developer retains status/reference permissions |
| Development | Select assigned records, edit eligible fields, inspect PR/build references | Same records and lifecycle evidence | Backend field and stage validation |
| QA | Test/defect details, criteria, linked stories and clarification threads | Same records and lifecycle evidence | QA roles; actual execution remains existing integrated test tools |
| Release | Linked release records, documentation, evidence and approval gate | Same records, evidence, transitions | Release role; no deployment success inferred |
| Documentation | Versioned editable documentation in each phase | Documentation work items and version history | Existing documentation roles; saved draft is not published approval |
| AI context | Inspect task and source artifact; use in draft or dismiss; retry existing run tools | Versioned agent artifact + durable annotation | Editing role, human session, current item/source version; explicit Save required |
| Traceability | Open upstream/downstream record from detail panel | Same project records and link_versions | Project membership |
| Shell | Keyboard command navigation; searchable record list | Existing routes and shared record state | Existing capabilities; no hidden API authorization bypass |

Project queue metrics now come from the same project work-item list used by the
workbench. Count buttons select the project before opening its phase. The approval
inbox filters authoritative `can_act` and `pending_approval`; missing-evidence queues
use the lifecycle response. Traceability matrix and discussion/history share record IDs.
QA users can create a linked draft defect from a test case and enter an observed failure
and actual execution reference. This does not synthesize a failed execution.

Past-phase records remain read-only in preview. An authorized BA can explicitly choose
“Revise requirement”; saving the amendment uses the existing backend invalidation rules.
