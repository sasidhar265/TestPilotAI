export function buildSettings(args = []) {
  const value = (name, fallback) => {
    const index = args.indexOf(name);
    if (index < 0) return fallback;
    if (!args[index + 1] || args[index + 1].startsWith("--"))
      throw new Error(`${name} needs a value`);
    return args[index + 1];
  };
  const development = args.includes("--development");
  const raw = value("--url", development ? "http://127.0.0.1:8000" : "");
  if (!raw)
    throw new Error(
      "Supply --url https://your-backend.example (or --development for local testing).",
    );
  const url = new URL(raw);
  if (url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error(
      "The backend URL must be an origin without credentials, a path, query or fragment.",
    );
  }
  if (url.protocol !== "https:" && !(development && url.protocol === "http:")) {
    throw new Error("HTTPS is required. HTTP is allowed only with --development.");
  }
  const appId = value("--app-id", "com.autofinancequality.mobile");
  if (!/^[a-zA-Z][\w]*(\.[a-zA-Z][\w]*){2,}$/.test(appId))
    throw new Error("Use a reverse-domain --app-id.");
  return { backend: url.origin, development, appId };
}

export function capacitorConfig(settings) {
  return {
    appId: settings.appId,
    appName: "Auto Finance Quality",
    webDir: "dist",
    // All UI is bundled. server.url is deliberately never used.
    server: { androidScheme: "https", cleartext: settings.development },
    android: { allowMixedContent: settings.development },
    ios: { contentInset: "automatic" },
    plugins: { CapacitorHttp: { enabled: true } },
  };
}
