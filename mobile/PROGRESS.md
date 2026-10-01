# Mobile work checkpoint — 2026-10-01

The unfinished workspace work is a Capacitor Android/iOS client for the existing
FastAPI application. Setup and device acceptance instructions are in `README.md`
in this folder. The original conversation's full requirements were unavailable
when resuming; this checkpoint records verified workspace state.

## Verified in this session

- `npm test`: 5 tests passed.
- `npm run test:ui`: 6 tests passed (3 Chromium Android-layout and 3 WebKit
  iPhone-layout tests). Covers authentication, navigation/reload, file selection,
  browser PDF download and connection-loss feedback.
- Android assets and plugins successfully built/synced with
  `npm run android -- --development --url http://10.0.2.2:8000`.
- iOS assets and plugins successfully built/synced with
  `npm run ios -- --development --url http://127.0.0.1:8000`.

Browser tests used their disposable test backend. They do not establish native
device behavior, AI workflow execution or generated API-pack BDD results.

## Remaining work requiring native tooling/configuration

- Install/select full Xcode and an iOS simulator runtime. `xcodebuild -version`
  currently fails because only standalone Command Line Tools are selected.
- Install/configure Android Studio and the Android SDK. Neither Android SDK
  environment variable is set, and the default SDK directory is absent.
- Compile and run both native apps, then perform the README device acceptance
  checks against a configured backend, including native sessions, uploads/sharing
  and real AI workflows.
- Configure an actual HTTPS release backend, owned identifiers, branding and
  signing before preparing signed releases. No store submission has occurred.

Both native projects currently contain development assets. The shared generated
`dist` and Capacitor configuration most recently came from the iOS preparation;
rerun the appropriate platform command before building that platform.
