# Delivery pipeline views

Each SDLC phase opens its working page directly. BA review exposes **View progress**
as a child navigation item beside its other review sections, replacing the workspace link.
The child navigation stays visible while inspecting BA progress and highlights that item.
It uses the same current-source review gate as the other child links.
For other stages, a secondary **View progress** link
opens the selected phase's agents, activity and delivery evidence, for example
`/sdlc?phase=qa&view=pipeline`. A **Back to [stage]** link returns to the work.
The former Stage workspace / Delivery pipeline tabs have been removed.
A separate right-hand workflow panel shows the delivery stages and their AI status.

The **Delivery progress** item under Specialist tools opens the complete run at
`/sdlc?view=pipeline`. Phase views also provide **View complete delivery pipeline**.
Browser history and reload preserve the selected view and phase.

On screens at least 1280 pixels wide, the workflow panel stays beside the stage workspace
as a sticky, independently scrollable container. On smaller screens it stacks below the
workspace. Its phase links navigate without advancing work. The selected phase and the
current human workflow are identified separately, so reviewing a later phase does not
imply its approval. The document-history view hides the workflow panel.

The existing backend phase policy supplies the relevant agent stages. BA review displays
requirements-agent output as review context; this does not assign approval to an agent.
The BA stage workspace presents business scope and expected deliverables first, followed
by expected benefits and their impact on the delivery journey. Each structured deliverable
includes its BRD quotation. Benefits distinguish explicit BRD statements from inferred
outcomes requiring BA confirmation; missing success measures remain unconfirmed.
Older assessments without structured deliverables require reassessment to populate them.
AI domain suggestions and the finding workbench follow the business context. A final BA
feedback and rework section hosts the existing human decision form, with prompts for both
business expectations and AI recommendations. Existing stage permissions, rework routing
and versioned decision history continue to apply.
The complete view shows all seven delivery agents. Stage views filter cards, activity,
artifacts, work breakdown and environment configuration to the relevant agent stages.
Run source and latest saved requirements versions remain visible for traceability.

All views reuse one selected run and the existing API handlers. Stop, resume and bundle
controls apply to the complete selected run, as explained in each scoped view. Navigation
does not start agents, transition lifecycle stages or approve work. Human review and
approval remain on the working page, with the existing server-owned permission and evidence
checks. The documentation/version-history view remains separate.

The BA navigation has five child items: Business overview, AI suggestions, Your decision,
Business documents, and View progress. Child links appear beneath BA review & approval
on its working and scoped progress views when the current saved source has both BA
and alignment assessments. Next stage saves the reviewed BRD and opens this workspace;
it does not advance the formal lifecycle or grant approval. A preview URL without
current-source assessments cannot reveal these links. Revising the BRD hides
the child links until those requirements are met again. The `review` query parameter
preserves the selected section across reloads, history navigation and progress views.

Verification used explicitly synthetic run artifacts for browser rendering. Those fixtures
are not actual build, test or deployment results. Nine affected browser checks passed,
including all eight workflow phases, activity/evidence filtering, URL/history/reload,
responsive layout and existing upload and BA approval flows. The right-panel update passed
ten browser checks, including side-by-side geometry at 1280/1440 pixels, stacked geometry
at 390/768 pixels and navigation that preserves the actual current handoff.

## Saved project documents and versions

The document archive at `/sdlc?view=documents` opens the saved BRD baseline by default.
Categories keep the document-view route when selected, and empty categories explain that
no output has been saved. Every saved version has a download button containing that
version's source text or structured snapshot; opening the archive never runs an agent.
BA review hides this separate archive and uses its Business documents downloads instead.
