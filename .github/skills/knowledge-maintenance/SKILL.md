---
name: knowledge-maintenance
description: Maintain scoped reference knowledge through draft, review, publish, rollback and withdrawal while preserving business-approval and memory boundaries.
---

# Knowledge maintenance

Use for application knowledge contributors and exact-match reuse, rather than adding business rules
implicitly from reference prose.

- Record a source reference, profile, domain, purpose and applicable workflow stages. Keep instructions
  and knowledge specific enough that the selected stages can use them without inventing extra scope.
- Saving creates a draft revision. Review the latest draft with a meaningful note, then publish it
  explicitly. Unpublished edits do not replace the active revision.
- Roll back only to a revision previously published through the existing workflow. Use withdrawal
  when a contributor should no longer be active; retain the revision and event history.
- Published contributors remain `reference_only`. Publication permits scoped reference use; it does
  not create approved business evidence or override mandatory policies and shared business rules.
- Respect revision conflicts and stage/profile context limits. Reload a conflicting edit instead of
  silently overwriting a later revision, and do not weaken publication checks to fit more context.
- Reuse only an applicable artifact that still passes validation. Changed source, approved handoffs,
  rules, profile or repository policy can invalidate generated reuse. Prior review feedback and a
  generated artifact are separate records; neither is a new execution result.

See [the versioned knowledge store](../../../app/knowledge_agents.py),
[workflow approval](../../guardrails/workflow-approval.md) and
[source trust](../../guardrails/source-trust.md). Browser-local custom agent descriptions are
reference definitions, not installed autonomous agents.
