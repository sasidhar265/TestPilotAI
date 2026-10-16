# Everyday workspace simplification

The default workflow now prioritizes project selection, requirements entry, review,
saving and the next accountable handoff. Existing records, handlers, permissions and
backend contracts are preserved.

- One Requirements Options disclosure groups business rules, test settings, AI delivery
  settings and finance context. Test and delivery settings use headings inside it rather
  than another layer of expandable menus.
- Work items use the list as their single selection control. The duplicate selector is
  hidden. Title, description, work status and acceptance criteria remain prominent;
  assignment, estimates, sprint, priority and links share one expandable section.
- Creating a linked defect reveals its supporting fields automatically.
- Stage checklists, saved-source previews, agent activity and document history are
  secondary disclosures. Required human decisions and evidence controls remain available.
- Plain action labels include Review requirements, Save requirements, Save changes and
  Discard draft. The landing page and navigation call the workflow Project workspace.
- Removed a decorative privacy badge and repeated heading copy; reduced nested cards,
  empty space and repeated empty-project prompts around the requirements editor.

Verification: 818 Python checks passed with isolated authentication settings; 153 opt-in
checks skipped in that run. Separately, 21 distinct browser checks passed across record
workflows, pasted/uploaded source persistence, BA report review and invalidation,
focused views, shared pages, themes and responsive layout. Keyboard navigation and URL
restoration were rechecked after the workspace title change. Ruff, JavaScript syntax
and diff-whitespace checks pass. This is a UI change, with no API/automation-pack contract
changes and no live-provider or deployment claims.

These checks establish working interactions and responsive presentation. They do not
replace feedback from representative first-time users on adoption.
