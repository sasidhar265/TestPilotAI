(() => {
  const storageKey = "quality-lifecycle-studio-theme";
  const legacyStorageKey = "testpilot-theme";
  const allowedThemes = new Set(["light", "dark", "system"]);
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  const gear = document.getElementById("theme-gear");
  const menu = document.getElementById("theme-menu");
  let preferredTheme = "system";
  const menuHome = menu?.parentElement;
  const menuSibling = menu?.nextSibling;

  function readPreference() {
    try {
      const saved = localStorage.getItem(storageKey) || localStorage.getItem(legacyStorageKey);
      return allowedThemes.has(saved) ? saved : "system";
    } catch {
      return "system";
    }
  }

  function resolvedTheme() {
    return preferredTheme === "system" ? (systemTheme.matches ? "dark" : "light") : preferredTheme;
  }

  function applyTheme() {
    const resolved = resolvedTheme();
    document.documentElement.dataset.theme = resolved;
    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) themeColor.content = resolved === "dark" ? "#10121a" : "#f5f6fa";
    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      const active = button.dataset.themeOption === preferredTheme;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function closeMenu() {
    if (!menu || !gear) return;
    menu.hidden = true;
    if (menu.classList.contains("theme-flyout")) {
      menuHome.insertBefore(menu, menuSibling);
      menu.classList.remove("theme-flyout");
      menu.style.removeProperty("left");
      menu.style.removeProperty("top");
    }
    gear.setAttribute("aria-expanded", "false");
  }

  preferredTheme = readPreference();
  applyTheme();

  gear?.addEventListener("click", () => {
    if (!menu) return;
    const opening = menu.hidden;
    closeMenu();
    if (
      opening &&
      gear.closest(".sidebar")?.dataset.collapsed === "true" &&
      matchMedia("(min-width: 1081px)").matches
    ) {
      document.body.append(menu);
      menu.classList.add("theme-flyout");
      menu.hidden = false;
      const anchor = gear.getBoundingClientRect();
      const bounds = menu.getBoundingClientRect();
      menu.style.left = `${Math.max(12, Math.min(anchor.right + 12, innerWidth - bounds.width - 12))}px`;
      menu.style.top = `${Math.max(12, Math.min(anchor.bottom - bounds.height, innerHeight - bounds.height - 12))}px`;
    }
    menu.hidden = !opening;
    gear.setAttribute("aria-expanded", String(opening));
    if (opening) menu.querySelector(".active")?.focus();
  });

  menu?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-theme-option]");
    if (!button) return;
    preferredTheme = button.dataset.themeOption;
    try {
      localStorage.setItem(storageKey, preferredTheme);
      localStorage.removeItem(legacyStorageKey);
    } catch {}
    applyTheme();
    closeMenu();
    gear?.focus();
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".theme-settings") && !menu?.contains(event.target)) closeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu && !menu.hidden) {
      closeMenu();
      gear?.focus();
    }
  });
  window.addEventListener("appearance-close", closeMenu);
  window.addEventListener("resize", closeMenu);
  systemTheme.addEventListener("change", () => {
    if (preferredTheme === "system") applyTheme();
  });
  window.addEventListener("storage", (event) => {
    if (event.key !== storageKey && event.key !== legacyStorageKey) return;
    preferredTheme = readPreference();
    applyTheme();
  });
})();
