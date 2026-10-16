# Workbench workflow alignment

`app/lifecycle_workflow.py` remains the sole project-stage policy. Agent run progress,
item delivery status and human lifecycle approval are distinct. Workflow actions stay
in the existing current-stage evidence and decision forms beside the record workbench.

A requirement edit creates a new immutable item version, reopens requirements analysis,
and invalidates prior approval through existing audit rules. BA review/validation evidence
must be current before requesting stakeholder approval. Stakeholder approval captures the
baseline and exact work-item versions in a human decision event; it covers the reviewed
requirement set, not an AI suggestion or an arbitrary item status. A comment never approves.

Inline edits use optimistic `base_version`; stale edits fail without replacing the draft.
Discussions and suggestion choices bind to an exact item version. Suggestions must refer
to a real latest agent artifact consuming the current BRD baseline. Using a suggestion
copies into an editable draft, with source references; only explicit save changes a record.
Human review annotations cannot grant a lifecycle gate. All reads enforce project membership.

The shared surface extends through backlog, development, QA, release and documentation.
Existing server gates continue to enforce owner assignment, dependency links, story readiness,
defect retesting and release evidence. Remote provider synchronization, automatic requirement
extraction into records, and live integration credentials remain tracked integration gaps.

Project BRD/requirements saving no longer attempts to modify the global shared-rules
file. Source-specific business rules are captured in the versioned source request.
The separate shared-rules publication action retains its existing permissions and is
hidden from roles that cannot perform it. No new global configuration permission was granted.
