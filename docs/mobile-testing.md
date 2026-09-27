# Mobile UI verification — 27 September 2026

## Scope

Browser-emulated touch testing against the repository's real HTML, CSS and JavaScript,
with deterministic mocked service responses. No production account or live finance API
was used. These checks do not establish physical iPhone/Android behavior, virtual-keyboard
resizing, or live backend integration.

The navigation matrix covers Quality workspace, Project dashboard, Progress & execution,
Quality Lifecycle, User guide, Documentation, Knowledge source, Runtime logs, Users and
API reference. Chromium viewports: 320×568, 390×844 and 768×1024. WebKit viewport: 390×844.
Additional Chromium and WebKit checks cover portrait 390×844 and landscape 844×390,
login controls, profile and notification panels, focus, scrolling and orientation changes.

## Findings and fixes

- The mobile drawer was only 40px tall at 320×568. The sidebar's backdrop filter established
  a containing block for its fixed child. Remove that filter in mobile navigation and size
  the drawer against the viewport below the measured header height.
- The menu header could scroll off-screen after opening Appearance. Keep the open header
  fixed, lock background scrolling, preserve its layout space, and restore the previous
  page scroll position on close.
- Escape closed both Appearance and navigation together. Close the innermost picker first;
  a subsequent Escape closes navigation and restores focus to the menu toggle.
- Close mobile navigation for all sidebar destination links, including documentation anchors.
  Reset open state on restored browser-history pages and release the scroll lock/inert state
  when resizing back to desktop.
- Visual review initially caught low-contrast colors during the theme transition. The final
  resolved dark-theme colors are correct; assert those colors before taking screenshots.

## Verification

Results: **44 mobile checks passed**. The broader existing browser suite passed **26 checks**.
After the final scroll-lock fix, the combined mobile, desktop navigation and workflow suite
was rerun: **54 passed in 132.79 seconds**. These runs cover 70 distinct browser checks in total.
JavaScript syntax, regression-test lint and whitespace checks also passed.

`tests/test_mobile_navigation_browser.py` contains 44 checks, including menu opening,
viewport bounds, 44px menu control, touch selection, dark mode, Escape, backdrop dismissal,
link navigation, focus wrapping, main-content isolation, scroll restoration, desktop resize,
login password visibility and profile/notification panel bounds.

The existing browser suites cover workflow approval/editing, BRD review, generated-suite
menus and downloads, script/report dialogs, execution records, dashboards, model selection,
review regeneration and lifecycle progress. These use mocked data, not live generated-pack
execution.

Run the focused mobile/navigation/workflow checks with:

```sh
RUN_BROWSER_TESTS=1 pytest -q tests/test_mobile_navigation_browser.py tests/test_navigation_theme_browser.py tests/test_workflow_browser.py
```

On this macOS environment, Chromium and WebKit require permission to launch outside the
filesystem sandbox. Screenshots are in `test-artifacts/mobile/`.
