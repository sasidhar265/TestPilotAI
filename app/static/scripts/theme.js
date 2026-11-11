/* Theme preferences are shared by Settings and the floating browser-local toggle. */
(() => {
  const storageKey = "quality-lifecycle-studio-theme";
  const legacyStorageKey = "testpilot-theme";
  const allowedThemes = new Set(["light", "dark", "system"]);
  const systemTheme = matchMedia("(prefers-color-scheme: dark)");
  function readPreference() {
    try {
      const saved = localStorage.getItem(storageKey) || localStorage.getItem(legacyStorageKey);
      return allowedThemes.has(saved) ? saved : "system";
    } catch {
      return "system";
    }
  }
  let preferredTheme = readPreference();
  function apply(value = preferredTheme) {
    const resolved = value === "system" ? (systemTheme.matches ? "dark" : "light") : value;
    document.documentElement.dataset.theme = resolved;
    const toggle = document.getElementById("floating-theme-toggle");
    if (toggle) {
      const label = resolved === "dark" ? "Switch to light theme" : "Switch to dark theme";
      toggle.setAttribute("aria-label", label);
      toggle.title = label;
      toggle.innerHTML = resolved === "dark"
        ? '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>'
        : '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 13A8.5 8.5 0 0 1 11 3.5 8.5 8.5 0 1 0 20.5 13Z"/></svg>';
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = resolved === "dark" ? "#10121a" : "#f5f6fa";
    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      const active = button.dataset.themeOption === value;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }
  window.workspaceTheme = {
    get: () => preferredTheme,
    preview: (value) => {
      if (allowedThemes.has(value)) apply(value);
    },
    save: (value) => {
      if (!allowedThemes.has(value)) return false;
      try {
        localStorage.setItem(storageKey, value);
        localStorage.removeItem(legacyStorageKey);
      } catch {
        return false;
      }
      preferredTheme = value;
      apply();
      return true;
    },
  };
  systemTheme.addEventListener("change", () => {
    if (preferredTheme === "system") apply();
  });
  window.addEventListener("storage", (event) => {
    if (event.key === storageKey || event.key === legacyStorageKey || event.key === null) {
      preferredTheme = readPreference();
      apply();
    }
  });
  if (window.self === window.top && !new URLSearchParams(location.search).has("appearance-preview")) {
    const toggle = document.createElement("button");
    toggle.id = "floating-theme-toggle";
    toggle.type = "button";
    toggle.className = "floating-theme-toggle";
    toggle.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      if (window.workspaceTheme.save(next)) {
        window.dispatchEvent(new CustomEvent("workspace-theme-changed", { detail: next }));
      }
    });
    document.body.append(toggle);
  }
  apply();
})();
