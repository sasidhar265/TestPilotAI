# Shared workspace presentation

The application keeps its existing teal/navy identity, plain HTML/CSS/JavaScript stack,
sidebar and route structure. Common appearance and orientation now apply to the seven
main workspace page shells rather than being maintained separately on each page.

## Shared components

| Component       | Convention                                                                                                   | Source                                  |
| --------------- | ------------------------------------------------------------------------------------------------------------ | --------------------------------------- |
| Page header     | One h1, Workspace breadcrumb, short purpose statement, existing account/actions                              | workspace-chrome.js                     |
| Page geometry   | Existing shared 40px desktop / responsive margins                                                            | page-alignment.css                      |
| Cards           | 14px radius, shared surface/border/shadow, 24px padding / 18px small-screen padding                          | workspace-ui.css                        |
| Typography      | Existing semantic type scale; 16px mobile inputs prevent browser input zoom                                  | typography.css, workspace-ui.css        |
| Forms           | Visible labels, consistent spacing, 44px dropdowns; multi-select lists use at least 132px                    | control-alignment.css, workspace-ui.css |
| Tables          | Shared cell spacing, header surface, separators and hover indication                                         | workspace-ui.css                        |
| Status labels   | Consistent badge geometry; retain text and existing semantic colours                                         | workspace-ui.css                        |
| Keyboard access | First-focus skip link, visible focus rings, focusable disclosure headings                                    | workspace-chrome.js, workspace-ui.css   |
| Motion          | Respect reduced-motion preference                                                                            | workspace-ui.css                        |
| Lifecycle       | Current stage and next action first; task forms together; full timeline, history and team details expandable | project-lifecycle.js                    |

`workspace-ui.css` loads last on index, documentation, knowledge, logs, users, API reference
and user-guide pages. It uses existing theme variables rather than introducing a second
palette. Page-specific layouts, charts, editors, navigation controls, role restrictions
and backend outcomes remain owned by their existing modules.

The login screen and standalone/offline finance reference remain specialised layouts.
Their existing identity is retained; the embedded reference keeps its own document structure.

## Behaviour and content

- Breadcrumb and purpose text update when the existing workspace changes views.
- Existing headings and navigation labels remain the source of page identity.
- Documentation and user-guide hero titles use h2; embedded documentation starts at h3.
- Lifecycle next-action text is derived from the backend's stage, ownership and missing
  evidence. It does not create a second workflow or infer approval from presentation.
- Team membership and record editing remain available through native disclosures.
- A multi-select is visually a list, rather than a dropdown that hides all its choices.

## Validation

Browser checks cover all seven page shells in light/dark themes at desktop and 390px
widths; single heading, breadcrumb, introductory copy, keyboard skip link, card geometry,
view switching and multi-select dimensions. Existing shared-view, theme, SDLC and mobile
navigation checks are run separately. The live human lifecycle journey verifies that the
presentation changes retain evidence submission, transitions, rework, persistence and
project/dashboard navigation. Execution results are recorded in IMPLEMENTATION_PROGRESS.md.

## Sequential SDLC navigation

The SDLC workspace reuses the existing numbered-step card style. Eight backend-defined
workspace groups show the lifecycle in order, with selected/current states distinguished.
The selected phase has its own description, substages, resource links and record list.
Previous/next controls preview a step; the human decision form makes the actual handoff.
On phones, the step bar scrolls horizontally inside its container instead of consuming
most of the screen or causing page overflow. Keyboard arrows/Home/End move focus and
Enter activates a step. Record drafts must be saved or explicitly cleared before switching.
