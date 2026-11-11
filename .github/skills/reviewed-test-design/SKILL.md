---
name: reviewed-test-design
description: Create or review source-grounded stories, scenario coverage and manual or automated test cases in the governed stage workflow.
---

# Reviewed test design

Apply the stage requested by the application: Requirements, Stories, Scenarios, then Test cases.
Do not return downstream artifacts when the current response schema requests an upstream stage.

- Ground stories in exact source excerpts and retain stable story and acceptance-criterion IDs.
- Build scenario coverage from the supplied reviewed handoff. Preserve story ownership and existing
  approvals; editing content invalidates affected approvals and downstream artifacts.
- Cover distinct positive, negative and boundary behavior supported by the source. Put unresolved
  business choices in questions or assumptions rather than executable passing expectations.
- Respect the selected output: manual, automation, non-functional or both. API and UI are the
  functional disciplines; performance and database are the existing non-functional choices.
  A non-functional route does not itself demonstrate a running performance or database test.
- Manual cases use observable ordered steps and no Gherkin. Automation cases include deterministic
  assertions, populated structured steps and executable Gherkin with the same meaning.
- Preserve requirement and scenario mappings. Do not reduce coverage to hit a sample size, create
  duplicate cases, or replace explicit source IDs with unrelated profile rules.
- Return the declared JSON schema. The application Quality Gate owns the structured design verdict;
  prose in assumptions or coverage notes must not supply a competing approval or execution claim.

See [feature standards](../../../workspace/feature-standards.md),
[approval boundaries](../../guardrails/workflow-approval.md) and the owning
[agent instructions](../../agents/README.md).
