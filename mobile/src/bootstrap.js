import { Capacitor } from "@capacitor/core";
import { App } from "@capacitor/app";
import { Browser } from "@capacitor/browser";
import { Filesystem, Directory } from "@capacitor/filesystem";
import { Share } from "@capacitor/share";
import { apiTarget, exportName } from "./transport.js";

const settings = __MOBILE_SETTINGS__;
const pages = __MOBILE_PAGES__;
const routes = __MOBILE_ROUTES__;
const native = Capacitor.isNativePlatform();
const originalFetch = window.fetch.bind(window);
const page = document.body.dataset.mobilePage;
const workspacePaths = new Set(["/", "/project-dashboard", "/progress", "/quality-lifecycle"]);
let banner;

function notice(message) {
  if (!banner) {
    banner = document.createElement("div");
    banner.className = "native-notice";
    banner.setAttribute("role", "status");
    document.body.append(banner);
  }
  banner.textContent = message;
  banner.hidden = !message;
}

window.fetch = async (input, options = {}) => {
  const target = apiTarget(input, location.href, native ? settings.backend : location.origin);
  const request = target && input instanceof Request ? new Request(target, input) : target || input;
  try {
    const response = await originalFetch(
      request,
      target ? { ...options, credentials: "include" } : options,
    );
    if (
      target &&
      response.status === 401 &&
      !target.endsWith("/api/auth/login") &&
      page !== "login.html"
    ) {
      location.replace("/login.html");
    }
    return response;
  } catch (error) {
    if (target)
      notice(
        navigator.onLine
          ? "Cannot reach the workspace. Check your connection and try again."
          : "You are offline. Reconnect to generate, upload or refresh results.",
      );
    throw error;
  }
};

async function saveFile(blob, filename) {
  if (blob.size > 25 * 1024 * 1024)
    throw new Error("For exports larger than 25 MB, use the desktop web app.");
  const data = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.readAsDataURL(blob);
  });
  const path = `mobile-exports/${Date.now()}-${exportName(filename)}`;
  const result = await Filesystem.writeFile({
    path,
    data,
    directory: Directory.Cache,
    recursive: true,
  });
  await Share.share({ title: filename, files: [result.uri], dialogTitle: "Save or share export" });
}

async function clearExports() {
  await Filesystem.rmdir({
    path: "mobile-exports",
    directory: Directory.Cache,
    recursive: true,
  }).catch(() => {});
}

window.MobileApp = {
  native,
  backend: settings.backend,
  saveFile: (blob, filename) =>
    saveFile(blob, filename).catch((error) =>
      notice(`Export could not be shared: ${error.message}`),
    ),
};

function localPage(url) {
  if (routes[url.pathname]) return `/${routes[url.pathname]}${url.search}${url.hash}`;
  return null;
}

document.addEventListener(
  "click",
  (event) => {
    const link = event.target.closest("a");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey)
      return;
    const url = new URL(link.href);
    if (native && link.hasAttribute("download")) {
      event.preventDefault();
      window
        .fetch(link.href)
        .then(async (response) => {
          if (!response.ok) throw new Error(`Download failed (${response.status})`);
          const filename = response.headers
            .get("content-disposition")
            ?.match(/filename="?([^";]+)"?/i)?.[1];
          await saveFile(
            await response.blob(),
            link.download || filename || url.pathname.split("/").pop(),
          );
        })
        .catch((error) => notice(error.message));
      return;
    }
    if (url.protocol !== location.protocol || url.host !== location.host) {
      if (native) {
        event.preventDefault();
        if (["https:", "http:"].includes(url.protocol))
          Browser.open({ url: url.href }).catch((error) => notice(error.message));
      }
      return;
    }
    const target = localPage(url);
    if (target) {
      event.preventDefault();
      location.assign(target);
    }
  },
  true,
);

async function start() {
  const expectedPage = routes[location.pathname];
  if (expectedPage && expectedPage !== page) {
    location.replace(`/${expectedPage}${location.search}${location.hash}`);
    return;
  }
  if (page === "index.html" && !workspacePaths.has(location.pathname))
    history.replaceState(null, "", "/");
  const canonical = Object.entries(routes).find(([, file]) => file === page)?.[0];
  if (canonical) history.replaceState(null, "", `${canonical}${location.search}${location.hash}`);
  if (page !== "login.html") {
    notice("Connecting to your workspace…");
    let timeout;
    const response = await Promise.race([
      fetch("/api/auth/profile"),
      new Promise((_, reject) => {
        timeout = setTimeout(
          () =>
            reject(
              new Error("The workspace did not respond. Check the backend connection and retry."),
            ),
          15000,
        );
      }),
    ]).finally(() => clearTimeout(timeout));
    if (!response.ok) {
      if (response.status === 401) return;
      throw new Error(`Workspace unavailable (${response.status}). Try again shortly.`);
    }
    const profile = await response.json();
    if (profile.is_guest) {
      location.replace("/login.html");
      return;
    }
  }
  // Keep the web app's classic scripts in their original order and global scope.
  for (const src of pages[page]) {
    await new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () =>
        reject(new Error("An application asset could not load. Restart the app."));
      document.body.append(script);
    });
  }
  notice("");
  document.body.classList.add("mobile-ready");
  if (native) {
    await clearExports();
    await App.addListener("backButton", () => {
      const openDialog = document.querySelector("dialog[open]");
      if (openDialog) {
        openDialog.close();
        return;
      }
      if (document.body.classList.contains("navigation-open")) {
        document.getElementById("sidebar-toggle")?.click();
        return;
      }
      if (location.pathname !== "/" && page !== "login.html") {
        location.assign("/");
        return;
      }
      App.minimizeApp();
    });
  }
  window.addEventListener("offline", () =>
    notice("You are offline. Reconnect to generate, upload or refresh results."),
  );
  window.addEventListener("online", () => notice("Connection restored. Retry your last action."));
}

start().catch((error) => {
  notice(error.message || "Cannot connect to the workspace.");
  const retry = document.createElement("button");
  retry.textContent = "Retry connection";
  retry.onclick = () => location.reload();
  banner.append(document.createElement("br"), retry);
});
