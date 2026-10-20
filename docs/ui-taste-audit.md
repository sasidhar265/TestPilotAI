# Workspace UI taste review

Applied the [Taste redesign skill](https://github.com/Leonxlnx/taste-skill/tree/main/skills/redesign-skill), stored at `.agents/skills/redesign-skill/SKILL.md`.

## Findings and changes

| Finding | Change |
| --- | --- |
| The eight-stage selector occupies space inside the editor. | Place all stages under SDLC workflow in the sidebar. Use normal links with active-page indicators, browser history and mobile drawer support. |
| Nested bordered cards and shadows give supporting content equal visual weight. | Remove shared card shadows and flatten the stage panel on desktop. Use simple separators for the saved baseline, checklist and activity disclosure. |
| Requirements repeats the stage heading with a second introductory block. | Hide the duplicate editor introduction only inside the SDLC requirements panel. Keep the heading in the standalone requirements tool. |
| Project selection and creation run together visually. | Align controls at the top and separate creation with a desktop divider. |
| Long introductions and proportional numeric columns slow scanning. | Limit introductory copy to 65 characters per line, balance headings and use tabular figures for tables and stage numbers. |
| Typeface and status silhouettes lack hierarchy. | Use a locally available Avenir/Segoe UI font stack and tighter status badge corners. No remote font requests or new packages. |
| Interaction feedback varies across controls. | Share visible keyboard outlines, restrained press feedback and 200ms colour transitions; respect reduced motion. |

The existing teal identity, semantic result colours, business content, handlers and approval flow remain authoritative. Decorative imagery, invented metrics, animation libraries and marketing-style effects do not help this data-heavy workspace and were not introduced.

## Verification scope

Browser checks use real HTML/CSS/JavaScript with synthetic API fixtures. They verify presentation and UI behaviour; they do not establish live provider, finance API, generated automation-pack or BDD execution results.

## Requirements simplification

The Requirements editor exposes document upload and Jira import through a + button inside the input. The menu supports keyboard focus, Escape dismissal and returning focus to the trigger. LLM selection, Validate requirements and Stop share an aligned action bar, with model availability feedback below it. Controls stack on mobile while the action buttons stay together. Validation uses the existing approved-source alignment endpoint and carries the selected provider and uploaded-document receipt. Stop cancels the in-flight validation request and requests server cancellation. It remains visible and disabled while idle, including after completed validation.

Business-rule editing, test output settings, delivery settings, BA review, generation buttons, proposed BRD downloads and workflow suggestions are removed from this tab. Validation results show the returned outcome and blocking reasons without proposed changes. Project selection remains available on the other SDLC stages. Existing runtime model restrictions remain enforced by the server.

The Requirements stage removes the duplicate Project workspace heading and stage list. Project selection and creation are available through the header project link in Documents, keeping duplicate setup controls out of Requirements. BA validation actions appear after a real baseline is saved. The selected stage names the page. The sidebar holds the policy-defined stages; legacy specialist URLs still work. Browser checks cover keyboard navigation, mobile drawer dismissal, browser back/reload and draft retention.

Documents and version history has its own sidebar destination at `/sdlc?view=documents`. It reuses project selection, artifact categories, saved documents, review history and version records. The focused view hides the lifecycle editor and next-action panels, opens the document ledger for the selected project, and restores that selection on reload.

## BRD summary and domain review

Document upload attaches a source and Jira import loads editable text; neither starts an LLM review. Choosing an LLM checks account access only. Clicking Validate requirements starts document extraction, the BRD summary and domain review, and approved-source alignment with the selected provider. The existing BA review endpoint supplies the high-level summary, objectives, scope, auto-finance domain assessment and knowledge metadata. The Requirements page displays these in Validation result & summary. It does not mark approved-source alignment as run until Validate requirements completes that separate check.

Explicit validation obtains the BA domain review, reusing an unchanged source review instead of calling the provider twice. Document extraction is reused for the same attached file, preserving its server receipt. Changed input or provider invalidates the displayed assessment. Auto-finance knowledge continues to be scoped and evidence-checked by the existing server-side BA agent; reference material does not become an approved business rule. Missing review results are shown as unavailable, and domain clarification findings remain visible even if approved-source alignment succeeds.

Browser fixtures cover document extraction, Jira import and invalid keys, provider forwarding, blocked results, cancellation, and light/dark responsive layouts. Shared workspace checks cover navigation, keyboard access and editor reuse.

## Confidence metrics and detailed report

The result includes BRD-to-domain confidence using the server's domain alignment percentage: covered topics divided by assessable in-scope topics, with equal weights. Knowledge gaps and out-of-scope topics are excluded. A score is displayed only when verified evidence and a positive assessable-topic count are returned; otherwise it reads Not assessable. This is a domain-alignment measure, not a calibrated probability or business approval.

Actual topic counts appear alongside a separately labelled illustrative sample calculation. Download detailed report exports a self-contained HTML document with the summary, actual metrics, all BA review areas and findings, every domain check, citations, complete assessment data and available reviewed-source traceability. Illustrative sample metrics are excluded from the download. Unavailable or partial reviews retain their reported state rather than becoming completed assessments.

Completed approved-source validation reports offer Next stage, using the next phase from the server's SDLC policy (currently Business approval). The button requires a selected project, saves the exact reviewed source and workflow snapshot, then opens the approval review with matching server assessments; it does not approve the BRD or advance lifecycle state. It remains disabled during work, is absent for canceled runs without a validation report, and disappears with the report when source input changes. Navigation controls are excluded from the downloaded report.
