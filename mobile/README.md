# Android and iOS application

This Capacitor application bundles the existing HTML, CSS and JavaScript from
`app/static`. FastAPI, AI providers, Jira credentials, databases and automation
execution stay on the backend. The desktop web application continues to work.

Included: Android Studio and Xcode projects, account sign-in, the existing quality
workflows, native export sharing, file-picker uploads, Android back handling,
safe-area layout and connection-loss feedback. This is an online application;
generation and execution require a reachable configured backend. Drafts are not
persisted across a full page reload or operating-system termination. Guest access
is not offered in the mobile app.

The native projects have been generated and synced. Browser checks are separate
from native device testing: native cookie persistence, file picking, sharing and
signed release builds still need verification on Android/iOS with their SDKs.
The application has not been submitted to either store.

## Prerequisites

- Node.js 22 or later; Python environment installed as described in the root README.
- Android: Android Studio 2025.2.1 or newer, its bundled JDK, Android SDK platform 36,
  build tools and an emulator system image. This project supports Android API 24+.
- iOS: macOS and Xcode 26 or newer, with an iOS simulator runtime installed. The
  project supports iOS 15+. It uses Swift Package Manager, not CocoaPods.

See the [Capacitor environment requirements](https://capacitorjs.com/docs/getting-started/environment-setup).
After installing full Xcode, select it in Xcode → Settings → Locations → Command
Line Tools. `xcodebuild -version` should report Xcode, rather than an error about
the standalone CommandLineTools installation.

## 1. Start your existing backend

From the repository root, configure your local `.env` with `APP_USERNAME`,
`APP_PASSWORD` and a strong `SESSION_SECRET`. These are the existing browser login
settings. Keep provider credentials on the backend. Never put `API_AUTH_TOKEN`,
passwords or AI credentials in the mobile configuration.

For local development, include the hostnames/IPs the clients will use:

```dotenv
ENVIRONMENT=development
ALLOWED_HOSTS=localhost,127.0.0.1,10.0.2.2
```

Keep your existing account settings, then start FastAPI:

```bash
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use `--host 127.0.0.1` if you only need the browser/iOS simulator. Binding to
`0.0.0.0` also permits LAN devices to reach the development server. Real phones
must use your computer's LAN IP, and that IP must also appear in `ALLOWED_HOSTS`.
Allow the port through your local firewall only as needed for testing.

Verify that you can sign in at `http://127.0.0.1:8000/login` first.

## 2. Test immediately in a browser

In another terminal:

```bash
cd mobile
npm ci
npm run dev -- --url http://127.0.0.1:8000
```

Open **http://127.0.0.1:5173** and sign in with your existing account. Use the
browser's responsive device toolbar for a phone-sized preview. This previews the
actual bundled pages, routing and backend calls. Its loopback-only proxy keeps
session cookies same-origin; it does not enable broad CORS on FastAPI.

Browser exports download normally. Native sharing and native cookie storage
require an emulator or real device. `npm run dev` rebuilds once at startup; restart
it after changing source files. Stop it before preparing native projects, since
both commands write the same generated `dist` and Capacitor configuration.

## 3. Run on an Android emulator

From `mobile`:

```bash
npm run android -- --development --url http://10.0.2.2:8000 --open
```

This rebuilds the assets, syncs plugins and opens Android Studio. Wait for Gradle
sync, select/create a device in **Device Manager**, select the **app** configuration
and press **Run**. Use the Debug build variant. `10.0.2.2` is the Android emulator's
address for the host computer; `127.0.0.1` would mean the emulator itself.

For a USB-connected Android phone, either use your LAN IP or run
`adb reverse tcp:8000 tcp:8000` and prepare the app with
`--url http://127.0.0.1:8000`. Enable USB debugging on that phone first.

## 4. Run on the iOS simulator

From `mobile`:

```bash
npm run ios -- --development --url http://127.0.0.1:8000 --open
```

In Xcode, allow Swift packages to resolve, choose the **App** scheme and an iPhone
simulator, then press **Run**. Simulator builds do not need App Store membership.
For a physical iPhone, select your signing team, enable Developer Mode, use your
computer's LAN IP in `--url`, and allow the app's local-network permission prompt.

HTTP is permitted in Debug platform settings and only when preparing assets with
`--development`. Release builds require an HTTPS backend; Android and Xcode release
checks reject assets that were prepared in development mode.

## Automated checks

From `mobile`:

```bash
npm test
npx playwright install chromium webkit
npm run test:ui
```

The UI suite starts a disposable FastAPI backend on port 8765 and a preview server
on port 5174. Keep those ports free. It uses temporary account/database storage and
does not load your `.env`. Its synthetic account is only for these local tests.
It exercises sign-in/out, bundled-page navigation and reloads, document selection,
browser PDF export and offline feedback at Android and iPhone viewport sizes.
It does not submit the document for AI ingestion or run AI generation, Jira writes
or automation packs. These are browser UI tests, not native-device or ReqnRoll API
results. API automation packs continue to use the existing BDD execution process.

## Device acceptance checks

Run this against a configured test backend on both platforms before release:

1. Sign in; close/reopen the app; confirm sessions expire and sign-out removes access.
2. Navigate all workspace pages, open/close the drawer and dialogs, rotate the
   device, and check keyboard/notch layouts. On Android, test the system Back button.
3. Select an actual supported PDF/DOCX/image and generate stories; review stories
   and scenarios, then generate and review the tests. This needs a working provider.
4. Export PDF/CSV/JSON/feature/ZIP artifacts; verify the OS share sheet can save them
   to Files/Downloads and that their contents match the reviewed suite. Exports
   above 25 MB are directed to the desktop web app to avoid native bridge limits.
5. View execution results from the configured backend. Only run reviewed test packs
   against their configured environment; a phone does not execute C# tests locally.
6. Turn off networking while editing; confirm the message, reconnect and retry.
   Force-quit and reopen offline to verify the connection-retry screen. Reloading
   clears unsaved drafts. Backgrounding may interrupt long operations; use the
   backend run history to check their actual outcome before retrying.

## Release preparation

Choose bundle/application identifiers owned by you. The initial identifier is
`com.autofinancequality.mobile`; update Android's application ID/namespace and Java
package, and Xcode's bundle identifier together if changing it. Pass the matching
`--app-id` on subsequent builds. The sync script refuses an inconsistent identifier.

Prepare each platform with your deployed backend, without `--development`:

```bash
npm run android -- --url https://your-backend.example
npm run ios -- --url https://your-backend.example
```

The backend URL is public configuration, bundled into the app. Native requests use
Capacitor's HTTP bridge and its cookie handling with the existing HttpOnly session;
no password or bearer token is saved in JavaScript storage. There is no remotely
loaded UI or `server.url`. Server authentication and authorization remain decisive.
Exports are held in the app's cache for sharing and cleared on the next page
startup. Copies saved or shared by the user are outside the application's cache.

Before submitting:

- Deploy and operate the backend with HTTPS, persistent storage/backups, appropriate
  account access and provider/worker configuration. Existing project IDs are not
  tenant isolation; this client does not turn the backend into a public multi-tenant SaaS.
- Replace the generated Capacitor launcher/splash artwork with approved branding,
  set version/build numbers and verify native behavior with the checklist above.
- Configure Android signing and build a signed AAB for Play testing; configure your
  Apple team, archive a Release build and upload it to TestFlight.
- Complete store listings, screenshots, support/privacy-policy URLs, reviewer access
  and accurate data/AI disclosures for your deployed service. The included iOS privacy
  manifest covers the Filesystem plugin's file-timestamp reason; it is not a complete
  declaration of the backend's data processing.
- Complete the stores' required testing and review. Billing, push notifications,
  offline editing and self-service account creation/deletion are not added here.

References: [native HTTP](https://capacitorjs.com/docs/apis/http),
[Filesystem privacy manifest](https://capacitorjs.com/docs/apis/filesystem),
[Apple review guidelines](https://developer.apple.com/app-store/review/guidelines/),
[Google Play setup](https://support.google.com/googleplay/android-developer/answer/6112435).

## Troubleshooting

| Symptom                                  | Check                                                                                                                   |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Preview reports backend unavailable      | FastAPI is running on the same port passed to `--url`.                                                                  |
| HTTP 400 / Invalid host header           | Add the emulator/LAN hostname to `ALLOWED_HOSTS`, then restart FastAPI.                                                 |
| Sign-in is unavailable                   | Configure both `APP_PASSWORD` and `SESSION_SECRET` on the backend.                                                      |
| Native app cannot connect                | Use the correct host address, Debug build and `--development` for local HTTP. Check firewall/local-network permissions. |
| Simulator build fails before compilation | Install full Xcode and select its command-line tools; allow Swift package resolution.                                   |
| Android SDK missing                      | Install SDK platform 36 in Android Studio and use its JDK.                                                              |
| Changes do not appear on device          | Rerun the appropriate `npm run android` / `npm run ios` command, then rebuild in the IDE.                               |
| Release says development backend         | Prepare that platform again with an HTTPS `--url` and no `--development`.                                               |
| Generation fails but sign-in works       | Configure the existing AI provider on the backend; the mobile client does not supply one.                               |
