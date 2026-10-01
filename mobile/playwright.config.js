import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/ui",
  fullyParallel: false,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:5174", trace: "retain-on-failure" },
  projects: [
    { name: "android-layout", use: { ...devices["Pixel 7"], browserName: "chromium" } },
    { name: "iphone-layout", use: { ...devices["iPhone 13"], browserName: "webkit" } },
  ],
  webServer: [
    {
      command: "../.venv/bin/python tests/serve_backend.py",
      url: "http://127.0.0.1:8765/api/live",
      reuseExistingServer: false,
    },
    {
      command: "node scripts/dev.mjs --url http://127.0.0.1:8765",
      url: "http://127.0.0.1:5174/login",
      env: { MOBILE_DEV_PORT: "5174" },
      reuseExistingServer: false,
    },
  ],
});
