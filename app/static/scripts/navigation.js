(() => {
  const sidebar = document.querySelector(".sidebar");
  const toggle = document.getElementById("sidebar-toggle");
  const content = document.getElementById("sidebar-content");
  if (!sidebar || !toggle || !content) return;
  // Keep the existing destinations and permissions; group infrequent tools together.
  const nav = sidebar.querySelector(".primary-nav");
  const financeNavigation = document.getElementById("finance-navigation");
  if (financeNavigation && !financeNavigation.querySelector('[href="/auto-finance-guide"]')) {
    const guide = document.createElement("a");
    guide.className = "nav-item";
    guide.href = "/auto-finance-guide";
    const label = document.createElement("span");
    label.textContent = "UK finance guide";
    guide.append(label);
    financeNavigation.prepend(guide);
  }
  financeNavigation?.querySelector('a[href="/products"]')?.remove();
  const knowledgeNavigation = document.getElementById("knowledge-navigation");
  const financeGroup = financeNavigation?.closest(".nav-group");
  if (knowledgeNavigation && !knowledgeNavigation.querySelector('a[href="/knowledge-agents"]')) {
    const link = document.createElement("a");
    link.className = "nav-item";
    link.href = "/knowledge-agents";
    const label = document.createElement("span");
    label.textContent = "Knowledge information";
    link.append(label);
    knowledgeNavigation.append(link);
  }
  if (knowledgeNavigation && financeNavigation && financeGroup) {
    knowledgeNavigation.append(...financeNavigation.querySelectorAll("a"));
    financeGroup.remove();
  }
  const labels = {
    "/progress": "Execution reports",
    "/quality-lifecycle": "Coverage & traceability",
    "/usage": "AI usage",
    "/knowledge": "Saved outputs",
    "/knowledge?view=domain": "Project knowledge & rules",
    "/knowledge?view=calculations": "Calculation checks",
  };
  nav.querySelectorAll("a").forEach((link) => {
    const url = new URL(link.href);
    const label = labels[url.pathname + url.search];
    if (label) link.querySelector("span:last-child").textContent = label;
  });
  nav.querySelectorAll(".nav-label").forEach((label) => {
    label.textContent = label.classList.contains("explore-nav-label") ? "Reference" : "Work";
  });
  if (!nav.querySelector('a[href="/agent-information"]')) {
    const link = document.createElement("a");
    link.className = "nav-item";
    link.href = "/agent-information";
    const label = document.createElement("span");
    label.textContent = "Agent information";
    const icon = document.createElement("span");
    icon.className = "nav-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "✧";
    link.append(icon, label);
    link.classList.toggle("active", location.pathname === "/agent-information");
    if (location.pathname === "/agent-information") link.setAttribute("aria-current", "page");
    nav.insertBefore(link, nav.querySelector(".explore-nav-label"));
  }
  nav.querySelectorAll('a[href="/settings"]').forEach((link) => link.remove());
  const profile = document.getElementById("profile-toggle")?.closest(".profile-menu");
  if (profile && !document.getElementById("settings-shortcut")) {
    const settings = document.createElement("a");
    settings.id = "settings-shortcut";
    settings.className = "avatar settings-shortcut";
    settings.href = "/settings";
    settings.title = "Settings";
    settings.setAttribute("aria-label", "Settings");
    settings.innerHTML =
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9.5 3-.6 2.1-1.6.9-2.1-.5-2.5 4.3 1.5 1.6v1.8l-1.5 1.6 2.5 4.3 2.1-.5 1.6.9.6 2.1h5l.6-2.1 1.6-.9 2.1.5 2.5-4.3-1.5-1.6v-1.8l1.5-1.6-2.5-4.3-2.1.5-1.6-.9-.6-2.1z"/><circle cx="12" cy="12" r="3"/></svg>';
    if (location.pathname === "/settings") settings.setAttribute("aria-current", "page");
    profile.before(settings);
  }
  const knowledgeSections = [
    [
      "Product understanding",
      "Your product as the agents read it",
      [
        [
          "Knowledge",
          "/knowledge?view=search",
          "Search reference content, rules, standards and saved-record summaries.",
        ],
        [
          "Product landscape",
          "/documentation#product-landscape",
          "Read how this application’s systems connect.",
        ],
        [
          "Services",
          "/documentation#knowledge-services",
          "Browse this repository’s service and module guide.",
        ],
        ["Code map", "/documentation#code-map", "View this repository’s folder-structure guide."],
        [
          "Business view",
          "/knowledge?view=domain",
          "Explore configured products, journeys, rules and terminology.",
        ],
      ],
    ],
    [
      "Memory",
      "Remembered context",
      [["Memory", "/knowledge?view=memory", "Review saved workflow records and approved outputs."]],
    ],
    [
      "Agent behavior",
      "How agents work",
      [
        [
          "Skills",
          "/documentation#knowledge-skills",
          "Read the conventions and framework guidance used by agents.",
        ],
        [
          "Prompts",
          "/documentation#knowledge-prompts",
          "Find agent instruction sources and prompt layering.",
        ],
        [
          "Guardrails",
          "/documentation#knowledge-guardrails",
          "Review workflow approval, access and model policies.",
        ],
      ],
    ],
  ];
  window.workspaceKnowledgeSections = knowledgeSections;
  const knowledgeHome = document.createElement("a");
  knowledgeHome.className = "nav-item";
  knowledgeHome.href = "/knowledge?view=overview";
  knowledgeHome.innerHTML =
    '<span class="nav-icon" aria-hidden="true">◈</span><span>Knowledge</span>';
  knowledgeHome.dataset.searchKeywords = knowledgeSections.flat(3).join(" ");
  nav.append(knowledgeHome);
  const knowledgePaths = knowledgeSections.flatMap(([, , items]) => items.map(([, path]) => path));
  const isKnowledgeDestination = () =>
    (location.pathname === "/knowledge" &&
      Boolean(new URLSearchParams(location.search).get("view"))) ||
    location.pathname === "/knowledge-agents" ||
    knowledgePaths.includes(location.pathname + location.search + location.hash);
  const links = new Map(
    [...nav.querySelectorAll("a")].map((link) => [link.getAttribute("href"), link]),
  );
  const groups = [
    ["workspace-agents", "Agents", "✧", ["/agent-information"]],
    ["knowledge-navigation", "Knowledge", "◈", ["/knowledge?view=overview"]],
    [
      "workspace-quality-engineering",
      "Quality Engineering",
      "✦",
      ["/", "/?view=stories", "/?view=scenarios", "/?view=test-cases", "/?view=automation"],
    ],
    ["workspace-data", "Data", "▤", ["/knowledge"]],
    [
      "workspace-delivery",
      "Delivery & Operations",
      "▦",
      ["/?view=execution", "/progress", "/logs"],
    ],
    ["workspace-ai-assure", "AI Assure", "◎", ["/quality-lifecycle", "/usage"]],
    [
      "workspace-administration",
      "Administration",
      "⚙",
      ["/admin/users", "/static/user-guide.html", "/documentation", "/docs"],
    ],
  ];
  const searchArea = document.createElement("div");
  searchArea.className = "workspace-nav-search";
  searchArea.innerHTML =
    '<label for="workspace-navigation-search"><span aria-hidden="true">⌕</span><input id="workspace-navigation-search" type="search" placeholder="Search navigation" aria-label="Search navigation" autocomplete="off" /></label>';
  const heading = document.createElement("span");
  heading.className = "nav-label";
  heading.textContent = "Workspace";
  const sections = groups.map(([id, title, icon, paths]) => {
    const group = document.createElement("div");
    group.className = "nav-group workspace-nav-section";
    if (id === "workspace-agents" || id === "knowledge-navigation") {
      group.id = id;
      const link = links.get(paths[0]);
      link.querySelector("span:last-child").textContent = title;
      const active =
        id === "workspace-agents"
          ? location.pathname === "/agent-information"
          : isKnowledgeDestination();
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      group.append(link);
      return group;
    }
    const parent = document.createElement("button");
    parent.type = "button";
    parent.className = "nav-item nav-parent";
    parent.setAttribute("aria-expanded", "false");
    parent.setAttribute("aria-controls", id);
    parent.innerHTML = `<span class="nav-icon" aria-hidden="true">${icon}</span><span>${title}</span><span class="nav-chevron" aria-hidden="true">⌄</span>`;
    const children = document.createElement("div");
    children.className = "nav-children";
    children.id = id;
    children.hidden = true;
    for (const path of paths) {
      const link = links.get(path);
      if (!link) continue;
      link.querySelector(".nav-icon")?.remove();
      if (path === "/admin/users") {
        link.classList.add("admin-navigation");
        link.dataset.permission = "admin";
        link.hidden = true;
      }
      children.append(link);
    }
    group.append(parent, children);
    return group;
  });
  const noResults = document.createElement("p");
  noResults.className = "workspace-nav-empty";
  noResults.setAttribute("role", "status");
  noResults.textContent = "No matching navigation items.";
  noResults.hidden = true;
  nav.replaceChildren(searchArea, heading, ...sections, noResults);
  const search = searchArea.querySelector("input");
  const expandedBeforeSearch = new Map();
  function filterNavigation() {
    const query = search.value.trim().toLowerCase();
    let count = 0;
    for (const section of sections) {
      const parent = section.querySelector(".nav-parent");
      const children = section.querySelector(".nav-children");
      if (!parent) {
        const link = section.querySelector("a");
        const match =
          !query ||
          `${link.textContent} ${link.dataset.searchKeywords || ""}`.toLowerCase().includes(query);
        const permitted = !link.hasAttribute("data-role-hidden") && !link.hidden;
        section.hidden = !match || !permitted;
        if (match && permitted) count++;
        continue;
      }
      if (query && !expandedBeforeSearch.has(section))
        expandedBeforeSearch.set(section, !children.hidden);
      let matches = 0;
      for (const link of children.querySelectorAll("a")) {
        const permitted = !link.hasAttribute("data-role-hidden") && !link.hidden;
        const match =
          !query ||
          `${parent.textContent} ${link.closest("[data-knowledge-category]")?.dataset.knowledgeCategory || ""} ${link.textContent}`
            .toLowerCase()
            .includes(query);
        link.toggleAttribute("data-search-hidden", !match);
        if (match && permitted) matches++;
      }
      for (const subsection of children.querySelectorAll(".knowledge-nav-subsection")) {
        subsection.hidden =
          Boolean(query) &&
          ![...subsection.querySelectorAll("a")].some(
            (link) =>
              !link.hasAttribute("data-search-hidden") && !link.hasAttribute("data-role-hidden"),
          );
      }
      section.hidden = query ? matches === 0 : false;
      if (query) {
        children.hidden = matches === 0;
        parent.setAttribute("aria-expanded", String(matches > 0));
      } else if (expandedBeforeSearch.has(section)) {
        children.hidden = !expandedBeforeSearch.get(section);
        parent.setAttribute("aria-expanded", String(!children.hidden));
        expandedBeforeSearch.delete(section);
      }
      count += matches;
    }
    noResults.hidden = !query || count > 0;
  }
  search.addEventListener("input", filterNavigation);
  search.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && search.value) {
      event.preventDefault();
      event.stopPropagation();
      search.value = "";
      filterNavigation();
    }
  });
  window.addEventListener("workspace-role-ready", filterNavigation);
  const hasHashDestination =
    Boolean(location.hash) &&
    [...nav.querySelectorAll("a")].some(
      (link) => link.getAttribute("href") === location.pathname + location.search + location.hash,
    );
  sidebar.querySelectorAll(".nav-parent").forEach((parent) => {
    const children = document.getElementById(parent.getAttribute("aria-controls"));
    let current = false;
    children.querySelectorAll("a").forEach((link) => {
      const target = new URL(link.href);
      const defaultView = target.pathname === "/" ? "requirements" : "saved";
      const view = target.searchParams.get("view") || defaultView;
      const active =
        location.pathname === target.pathname &&
        (target.hash
          ? target.hash === location.hash
          : !hasHashDestination && !isKnowledgeDestination()) &&
        (target.pathname === "/knowledge"
          ? document.body.dataset.knowledgeView || "saved"
          : new URLSearchParams(location.search).get("view") || defaultView) === view;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      current ||= active;
    });
    children.hidden = !current;
    parent.classList.toggle("active", current);
    parent.setAttribute("aria-expanded", String(current));
    parent.title = parent.querySelector("span:nth-child(2)").textContent;
    parent.addEventListener("click", () => {
      if (!mobile.matches && sidebar.dataset.collapsed === "true") {
        desktopCollapsed = false;
        setCollapsed(false);
        try {
          localStorage.setItem(storageKey, "false");
        } catch {}
        children.hidden = false;
      } else children.hidden = !children.hidden;
      parent.setAttribute("aria-expanded", String(!children.hidden));
    });
  });
  window.addEventListener("hashchange", () => {
    const link = document.querySelector("#knowledge-navigation > a");
    const active = isKnowledgeDestination();
    link.classList.toggle("active", active);
    if (active) {
      nav.querySelectorAll('a[aria-current="page"]').forEach((other) => {
        if (other !== link) {
          other.classList.remove("active");
          other.removeAttribute("aria-current");
        }
      });
      link.setAttribute("aria-current", "page");
    } else link.removeAttribute("aria-current");
  });
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
    link.title = link.dataset.description ? `${text} — ${link.dataset.description}` : text;
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
    sidebar.dataset.collapsed = String(collapsed);
    content.hidden = mobile.matches && collapsed;
    backdrop.hidden = !mobile.matches || collapsed;
    setMobileOpen(mobile.matches && !collapsed);
    document.querySelector("main").inert = mobile.matches && !collapsed;
    toggle.setAttribute("aria-expanded", String(!collapsed));
    const label = collapsed ? "Expand navigation" : "Collapse navigation";
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
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
      const controls = [
        ...sidebar.querySelectorAll("a[href], button:not(:disabled), input:not(:disabled)"),
      ].filter((element) => element.getClientRects().length);
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
