---
name: workspace-customization
description: Maintain the application's Requirements landing page, navigation, appearance settings and preview/save behavior when changing the workspace UI.
---

# Workspace customization

Use for application UI maintenance. These controls run in local application code; this skill is
maintainer guidance and is not automatically attached to test-generation agents.

- Requirements at `/` is the home page after login for every role. Preserve role-scoped actions,
  source upload, configured Jira import and existing test-output/provider controls.
- Preserve sidebar search, the Agents and Knowledge destinations and the grouped workspace tools.
  Settings is the gear beside the profile control; theme switching uses the floating corner button.
- Keep branding, background, fonts, labels and navigation icons configurable through Settings.
  Draft appearance changes affect the preview; Save applies the persisted appearance to main pages.
  Expanded preview is a modal overlay, not a navigation away from the settings editor.
- Derive readable foreground and surface colors from workspace tokens. Check light/dark themes,
  small screens, keyboard focus, modal dismissal and reduced-motion behavior for affected controls.
- Keep Requirements drafts intact during workspace navigation. A presentation change must not
  submit a form, publish knowledge, start generation or run tests as a side effect.
- Do not expose credentials or model-policy overrides as branding preferences. Preserve API-side
  permissions rather than relying on hidden navigation controls for authorization.

See the [appearance implementation](../../../app/static/scripts/appearance.js),
[workspace navigation](../../../app/static/scripts/workspace-pages.js) and
[Settings page](../../../app/static/settings.html). Browser checks verify layout and interaction;
they do not establish execution evidence for generated automation packs.
