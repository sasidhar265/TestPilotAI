/* Shared, server-persisted branding. Labels never alter routes or permissions. */
(() => {
  const fonts = {
    system: 'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    arial: "Arial, Helvetica, sans-serif",
    georgia: 'Georgia, "Times New Roman", serif',
    verdana: "Verdana, Geneva, sans-serif",
    mono: "ui-monospace, Menlo, Consolas, monospace",
  };
  let current;
  const defaults = new Map();
  const brand = document.querySelector(".brand");
  const originalMark = brand?.querySelector(".brand-mark")?.cloneNode(true);
  function navigationItems() {
    return [
      ...document.querySelectorAll(
        ".primary-nav a, .primary-nav .nav-parent, .primary-nav > .nav-label",
      ),
    ]
      .map((node) => {
        const key = node.matches("a")
          ? `link:${node.getAttribute("href")}`
          : node.matches("button")
            ? `group:${node.getAttribute("aria-controls")}`
            : `section:${node.classList.contains("explore-nav-label") ? "reference" : "workspace"}`;
        const label = node.matches(".nav-label")
          ? node
          : node.querySelector("span:not(.nav-icon):not(.nav-chevron)");
        if (!label) return null;
        if (!defaults.has(key))
          defaults.set(key, {
            key,
            label: label.textContent.trim(),
            icon: node.querySelector(".nav-icon")?.textContent || "",
          });
        return { key, node, label, defaults: defaults.get(key) };
      })
      .filter(Boolean);
  }
  // WCAG relative luminance: choose colours against the actual rendered surfaces.
  const rgb = (hex) => hex.match(/[a-f0-9]{2}/gi).map((part) => parseInt(part, 16));
  const hex = (channels) =>
    "#" + channels.map((n) => Math.round(n).toString(16).padStart(2, "0")).join("");
  const mix = (a, b, amount) => hex(rgb(a).map((n, i) => n * (1 - amount) + rgb(b)[i] * amount));
  function luminance(colour) {
    const linear = rgb(colour).map((n) => {
      const value = n / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
  }
  function contrast(a, b) {
    const values = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (values[0] + 0.05) / (values[1] + 0.05);
  }
  let paletteKeys = [];
  function applyPalette(background) {
    const root = document.documentElement;
    for (const key of paletteKeys) root.style.removeProperty(key);
    paletteKeys = [];
    root.style.removeProperty("color-scheme");
    delete root.dataset.backgroundTone;
    if (!/^#[a-f0-9]{6}$/i.test(background)) return;
    const dark = contrast("#ffffff", background) > contrast("#000000", background);
    const end = dark ? "#ffffff" : "#000000";
    const surface = mix(background, dark ? "#000000" : "#ffffff", dark ? 0.4 : 0.9);
    const soft = mix(background, surface, 0.65);
    const tinted = mix(surface, dark ? "#000000" : "#ffffff", 0.2);
    const backgrounds = [background, surface, soft, tinted];
    function readable(candidate, targets = backgrounds, ratio = 4.5) {
      for (let step = 0; step <= 100; step++) {
        const colour = mix(candidate, end, step / 100);
        if (targets.every((target) => contrast(colour, target) >= ratio)) return colour;
      }
      return end;
    }
    const primary = readable("#6366f1");
    const primarySoft = mix(surface, primary, 0.08);
    const successSoft = mix(surface, "#22c55e", 0.06);
    const warningSoft = mix(surface, "#f59e0b", 0.06);
    const dangerSoft = mix(surface, "#ef4444", 0.06);
    const allSurfaces = [...backgrounds, primarySoft, successSoft, warningSoft, dangerSoft];
    const ink = readable(dark ? "#f8fafc" : "#172033", allSurfaces);
    const palette = {
      "--bg": background,
      "--surface": surface,
      "--surface-soft": soft,
      "--soft": soft,
      "--surface-tint": tinted,
      "--ink": ink,
      "--ink-soft": readable("#64748b", allSurfaces),
      "--muted": readable("#8090a8", allSurfaces),
      "--line": mix(surface, end, 0.22),
      "--line-strong": mix(surface, end, 0.4),
      "--primary": readable(primary, allSurfaces),
      "--primary-dark": readable(primary, allSurfaces),
      "--primary-soft": primarySoft,
      "--on-primary":
        contrast("#ffffff", primary) >= contrast("#000000", primary) ? "#ffffff" : "#000000",
      "--on-ink": contrast("#ffffff", ink) >= contrast("#000000", ink) ? "#ffffff" : "#000000",
      "--success": readable("#16834a", allSurfaces),
      "--success-soft": successSoft,
      "--warning": readable("#a66308", allSurfaces),
      "--warning-soft": warningSoft,
      "--danger": readable("#c33d55", allSurfaces),
      "--danger-soft": dangerSoft,
      "--shadow-sm": `0 2px 12px rgb(0 0 0 / ${dark ? "25%" : "8%"})`,
      "--shadow-md": `0 14px 36px rgb(0 0 0 / ${dark ? "40%" : "14%"})`,
    };
    // Derive button text from the final, contrast-adjusted accent.
    palette["--on-primary"] =
      contrast("#ffffff", palette["--primary"]) >= contrast("#000000", palette["--primary"])
        ? "#ffffff"
        : "#000000";
    for (const [key, value] of Object.entries(palette)) root.style.setProperty(key, value);
    paletteKeys = Object.keys(palette);
    root.style.colorScheme = dark ? "dark" : "light";
    root.dataset.backgroundTone = dark ? "dark" : "light";
  }
  function apply(settings) {
    current = settings;
    const root = document.documentElement;
    root.style.setProperty("--font-ui", fonts[settings.font_family] || fonts.system);
    root.style.fontSize = `${settings.font_size}px`;
    root.dataset.customAppearance = "true";
    root.toggleAttribute("data-custom-background", Boolean(settings.background));
    if (settings.background) root.style.setProperty("--workspace-background", settings.background);
    else root.style.removeProperty("--workspace-background");
    applyPalette(settings.background);
    const title = brand?.querySelector("strong");
    const subtitle = brand?.querySelector("small");
    if (title) title.textContent = settings.title;
    if (subtitle) subtitle.textContent = settings.subtitle;
    if (brand) brand.setAttribute("aria-label", `${settings.title} home`);
    const mark = brand?.querySelector(".brand-mark");
    if (mark) {
      mark.replaceChildren();
      if (settings.logo) {
        const img = document.createElement("img");
        img.src = settings.logo;
        img.alt = "";
        mark.append(img);
      } else if (originalMark)
        mark.replaceChildren(...[...originalMark.childNodes].map((node) => node.cloneNode(true)));
    }
    for (const item of navigationItems()) {
      const value = settings.navigation[item.key] || item.defaults;
      item.label.textContent = value.label;
      if (!item.node.matches(".nav-label")) {
        item.node.title = item.node.dataset.description
          ? `${value.label} — ${item.node.dataset.description}`
          : value.label;
        item.node.setAttribute("aria-label", value.label);
        let icon = item.node.querySelector(".nav-icon");
        if (!icon && value.icon) {
          icon = document.createElement("span");
          icon.className = "nav-icon";
          icon.setAttribute("aria-hidden", "true");
          item.node.prepend(icon);
        }
        if (icon) icon.textContent = value.icon;
      }
    }
    syncPageTitle();
  }
  function syncPageTitle() {
    if (!current) return;
    const pageTitle = document.querySelector(".topbar h1")?.textContent.trim();
    const next = pageTitle ? `${pageTitle} — ${current.title}` : current.title;
    if (document.title !== next) document.title = next;
  }
  // Page-specific scripts also change titles after asynchronous loads and hash navigation.
  const pageTitle = document.querySelector("title");
  if (pageTitle) new MutationObserver(syncPageTitle).observe(pageTitle, {
    childList: true, subtree: true, characterData: true,
  });
  window.workspaceAppearance = {
    apply,
    navigation: () =>
      navigationItems().map((item) => ({
        ...item.defaults,
        group:
          item.node.closest(".nav-children")?.id ||
          item.node.getAttribute("aria-controls") ||
          (item.node.matches(".nav-label") ? "sections" : "work"),
      })),
    publish: (settings) => {
      apply(settings);
      try {
        localStorage.setItem("workspace-appearance-updated", `${Date.now()}-${Math.random()}`);
      } catch {}
    },
    get: () => current,
  };
  const initialSettings = window.workspaceAppearanceRequest ||
    fetch("/api/appearance", { cache: "no-store" }).then(async (response) => {
      if (!response.ok) throw new Error("Application settings are unavailable");
      return response.json();
    });
  window.appearanceReady = initialSettings.then((settings) => {
    apply(settings);
    return settings;
  }).finally(() => {
    window.workspaceAppearanceTitleGuard?.disconnect();
    if (!current) document.title = document.querySelector(".topbar h1")?.textContent || "Workspace";
    document.documentElement.removeAttribute("data-appearance-pending");
  });
  window.appearanceReady.catch(() => {});
  window.addEventListener("storage", async (event) => {
    if (
      event.key !== "workspace-appearance-updated" ||
      new URLSearchParams(location.search).has("appearance-preview")
    )
      return;
    try {
      const response = await fetch("/api/appearance", { cache: "no-store" });
      if (response.ok) apply(await response.json());
    } catch {
      /* Keep the last applied appearance while the service is unavailable. */
    }
  });
  window.addEventListener("workspace-page-changed", () => {
    if (current) apply(current);
  });
})();
