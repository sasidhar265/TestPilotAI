(() => {
  const sidebar = document.querySelector(".sidebar");
  const toggle = document.getElementById("sidebar-toggle");
  const content = document.getElementById("sidebar-content");
  if (!sidebar || !toggle || !content) return;
  const mobile = matchMedia("(max-width: 1080px)");
  const storageKey = "quality-lifecycle-navigation-collapsed";
  const backdrop = document.createElement("button");
  backdrop.className = "navigation-backdrop";
  backdrop.type = "button";
  backdrop.tabIndex = -1;
  backdrop.setAttribute("aria-label", "Close navigation");
  backdrop.hidden = true;
  document.body.append(backdrop);
  const placeholder = document.createElement("div");
  placeholder.className = "navigation-placeholder";
  placeholder.setAttribute("aria-hidden", "true");
  sidebar.after(placeholder);
  let lockedScroll = null;
  function setMobileOpen(open) {
    if (open && !lockedScroll) {
      lockedScroll = { top: window.scrollY, left: window.scrollX };
      document.body.style.setProperty("--navigation-scroll-top", `${-lockedScroll.top}px`);
    }
    document.body.classList.toggle("navigation-open", open);
    document.documentElement.classList.toggle("navigation-open", open);
    if (!open && lockedScroll) {
      const previous = lockedScroll;
      lockedScroll = null;
      document.body.style.removeProperty("--navigation-scroll-top");
      window.scrollTo({ ...previous, behavior: "instant" });
    }
  }
  sidebar.querySelectorAll(".primary-nav a").forEach((link) => {
    const label = link.textContent.trim();
    const text = link.querySelector("span:last-child")?.textContent.trim() || label;
    link.setAttribute("aria-label", text);
    link.title = text;
  });
  backdrop.addEventListener("click", () => {
    setCollapsed(true);
    toggle.focus();
  });
  let desktopCollapsed = false;
  try {
    desktopCollapsed = localStorage.getItem(storageKey) === "true";
  } catch {}
  function setCollapsed(collapsed) {
    window.dispatchEvent(new Event("appearance-close"));
    sidebar.dataset.collapsed = String(collapsed);
    content.hidden = mobile.matches && collapsed;
    backdrop.hidden = !mobile.matches || collapsed;
    setMobileOpen(mobile.matches && !collapsed);
    document.querySelector("main").inert = mobile.matches && !collapsed;
    toggle.setAttribute("aria-expanded", String(!collapsed));
    const label = collapsed ? "Expand navigation" : "Collapse navigation";
    toggle.setAttribute("aria-label", label);
    toggle.title = label;

    if (collapsed) {
      const themeMenu = document.getElementById("theme-menu");
      if (themeMenu) themeMenu.hidden = true;
      document.getElementById("theme-gear")?.setAttribute("aria-expanded", "false");
    }
  }
  toggle.addEventListener("click", () => {
    const collapsed = sidebar.dataset.collapsed !== "true";
    setCollapsed(collapsed);
    if (!mobile.matches) {
      desktopCollapsed = collapsed;
      try {
        localStorage.setItem(storageKey, String(collapsed));
      } catch {}
    }
  });
  sidebar.addEventListener("keydown", (event) => {
    if (event.key === "Tab" && mobile.matches && !content.hidden) {
      const controls = [...sidebar.querySelectorAll("a[href], button:not(:disabled)")].filter(
        (element) => element.getClientRects().length,
      );
      const first = controls[0],
        last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    if (event.key === "Escape" && mobile.matches && !content.hidden) {
      // Let the theme picker handle its own Escape before dismissing the drawer.
      if (document.getElementById("theme-menu")?.hidden === false) return;
      event.preventDefault();
      event.stopPropagation();
      setCollapsed(true);
      toggle.focus();
    }
  });
  sidebar.querySelectorAll("a[href]").forEach((link) =>
    link.addEventListener("click", () => {
      if (mobile.matches) setCollapsed(true);
    }),
  );
  const updateHeaderHeight = () => {
    if (mobile.matches) {
      const height = `${sidebar.getBoundingClientRect().height}px`;
      sidebar.style.setProperty("--navigation-header-height", height);
      placeholder.style.height = height;
    }
  };
  new ResizeObserver(updateHeaderHeight).observe(sidebar);
  mobile.addEventListener("change", () => {
    setCollapsed(mobile.matches || desktopCollapsed);
    updateHeaderHeight();
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) setCollapsed(mobile.matches || desktopCollapsed);
  });
  setCollapsed(mobile.matches || desktopCollapsed);
})();
