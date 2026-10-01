import test from "node:test";
import assert from "node:assert/strict";
import { buildSettings, capacitorConfig } from "../scripts/config.mjs";
import { apiTarget, exportName } from "../src/transport.js";

test("release configuration requires HTTPS and packages UI locally", () => {
  assert.throws(() => buildSettings([]), /Supply --url/);
  assert.throws(() => buildSettings(["--url", "http://example.com"]), /HTTPS/);
  const settings = buildSettings(["--url", "https://example.com"]);
  const config = capacitorConfig(settings);
  assert.equal(config.server.url, undefined);
  assert.equal(config.server.cleartext, false);
  assert.equal(config.android.allowMixedContent, false);
  assert.equal(config.plugins.CapacitorHttp.enabled, true);
});

test("URLs cannot embed credentials or change the backend base path", () => {
  for (const url of [
    "https://user:pass@example.com",
    "https://example.com/api",
    "https://example.com?token=secret",
    "https://example.com/#secret",
    "file:///tmp/a",
  ]) {
    assert.throws(() => buildSettings(["--url", url]));
  }
  assert.throws(() => buildSettings(["--url"]), /needs a value/);
});

test("local HTTP is explicit and supports the Android emulator host", () => {
  const settings = buildSettings(["--development", "--url", "http://10.0.2.2:8000"]);
  assert.equal(settings.backend, "http://10.0.2.2:8000");
  assert.equal(capacitorConfig(settings).server.cleartext, true);
});

test("transport maps only local API paths and preserves encoded queries", () => {
  const local = "capacitor://localhost";
  // URL.origin for a custom scheme is "null", so callers use the actual webview base URL.
  assert.equal(
    apiTarget("/api/items?a=x%20y", "https://localhost", "https://backend.example"),
    "https://backend.example/api/items?a=x%20y",
  );
  assert.equal(
    apiTarget("/static/scripts/index.js", "https://localhost", "https://backend.example"),
    null,
  );
  assert.equal(
    apiTarget(
      "https://untrusted.example/api/items",
      "https://localhost",
      "https://backend.example",
    ),
    null,
  );
  assert.equal(
    apiTarget("/openapi.json", "https://localhost", "https://backend.example"),
    "https://backend.example/openapi.json",
  );
  assert.equal(
    apiTarget("/api/items", local, "https://backend.example"),
    "https://backend.example/api/items",
  );
});

test("export names cannot escape the app cache folder", () => {
  assert.equal(exportName("../../report.zip"), "report.zip");
  assert.equal(exportName("C:\\exports\\test.csv"), "test.csv");
  assert.equal(exportName(""), "export");
});
