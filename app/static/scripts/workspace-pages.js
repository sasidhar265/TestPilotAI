/* Switch focused views without replacing the shared workflow or its drafts. */
(() => {
  const titles = {
    "/sdlc": "Project workspace",
    "/project-dashboard": "Project dashboard",
    "/": "Requirements",
    "/progress": "Execution reports",
    "/quality-lifecycle": "Coverage & traceability",
    "/products": "Products",
    "/auto-finance-guide": "UK finance guide",
    "/usage": "AI usage",
  };
  const sdlcStages = {
    planning: "Planning",
    design: "Architecture",
    development: "Development",
    requirements: "Business analysis",
    testing: "Testing",
    release: "Release",
    operations: "Operations",
  };
  const views = Object.fromEntries(window.workflowStages.map((stage) => [stage.view, stage.title]));
  // Keep generation context controls beside the requirements they govern.
  document
    .querySelector(".panel.composer")
    .append(document.querySelector(".finance-context-settings"));
  const stageNavigation = document.createElement("section");
  stageNavigation.className = "workflow-navigation";
  stageNavigation.setAttribute("aria-label", "Quality workflow navigation");
  stageNavigation.append(
    document.querySelector(".stage-navigation-heading"),
    document.querySelector(".stage-tabs"),
  );
  let displayedUrl = location.pathname + location.search;
  function showPage(focus = false) {
    if (location.pathname === "/products")
      history.replaceState(null, "", "/auto-finance-guide?section=products");
    if (
      location.pathname === "/" &&
      new URLSearchParams(location.search).get("view") === "ba-agent"
    )
      history.replaceState(null, "", "/?view=requirements");
    if (document.body.dataset.guest === "true" && location.pathname !== "/")
      history.replaceState(null, "", "/");
    // The lifecycle is the landing page; explicit tool URLs remain compatible.
    if (
      document.body.dataset.guest !== "true" &&
      location.pathname === "/" &&
      !new URLSearchParams(location.search).has("view")
    )
      history.replaceState(null, "", "/sdlc" + location.search);
    const path = location.pathname;
    document.body.dataset.workspacePath = path;
    const requested = new URLSearchParams(location.search).get("view") || "requirements";
    const view =
      path === "/products" ? "products" : requested in views ? requested : "requirements";
    document.body.dataset.qualityView = view;
    const pagePath =
      path === "/products" ? "/" : path === "/" && view === "automation" ? `/${view}` : path;
    document.querySelectorAll("[data-workspace-page]").forEach((page) => {
      page.hidden = page.dataset.workspacePage !== pagePath;
    });
    if (path === "/auto-finance-guide") {
      const frame = document.getElementById("auto-finance-guide-frame");
      if (new URLSearchParams(location.search).get("section") === "products") {
        const revealProducts = () =>
          requestAnimationFrame(() => {
            const target = frame.contentDocument?.getElementById("products");
            if (target)
              window.scrollTo({
                top:
                  window.scrollY +
                  frame.getBoundingClientRect().top +
                  target.getBoundingClientRect().top,
                behavior: "smooth",
              });
          });
        if (frame.contentDocument?.getElementById("products")) revealProducts();
        else frame.addEventListener("load", revealProducts, { once: true });
      }
      if (!frame.getAttribute("src")) frame.src = "/static/auto-finance-uk.html?embedded=1";
    }
    const navigationHost = document.querySelector(`[data-workspace-page="${pagePath}"]`);
    stageNavigation.hidden = path !== "/";
    if (path !== "/")
      stageNavigation.querySelectorAll('[role="tab"]').forEach((tab, index) => {
        tab.setAttribute("aria-selected", "false");
        tab.tabIndex = index === 0 ? 0 : -1;
      });
    if (navigationHost) {
      if (path !== "/") {
        navigationHost.append(stageNavigation);
      } else {
        const hero = navigationHost.querySelector(".finance-hero");
        if (view === "requirements" && hero) hero.after(stageNavigation);
        else navigationHost.prepend(stageNavigation);
      }
    }
    document.querySelectorAll("[data-quality-view]").forEach((section) => {
      if (section !== document.body) section.hidden = section.dataset.qualityView !== view;
    });
    document.querySelectorAll(".primary-nav a").forEach((link) => {
      const active =
        link.pathname === path &&
        (path !== "/sdlc" ||
          (new URL(link.href).searchParams.get("stage") || "") ===
            (new URLSearchParams(location.search).get("stage") || "")) &&
        (path !== "/" || (new URL(link.href).searchParams.get("view") || "requirements") === view);
      link.classList.toggle("active", active);
      if (active) {
        link.setAttribute("aria-current", "page");
        link.closest("details")?.setAttribute("open", "");
      } else link.removeAttribute("aria-current");
    });
    document.querySelectorAll(".nav-parent").forEach((parent) => {
      const children = document.getElementById(parent.getAttribute("aria-controls"));
      const active =
        Boolean(children.querySelector('[aria-current="page"]')) ||
        (parent.getAttribute("aria-controls") === "sdlc-navigation" &&
          [
            "/",
            "/sdlc",
            "/project-dashboard",
            "/progress",
            "/quality-lifecycle",
            "/usage",
          ].includes(path));
      parent.classList.toggle("active", active);
      if (active) {
        children.hidden = false;
        parent.setAttribute("aria-expanded", "true");
      }
    });
    const selectedStage = new URLSearchParams(location.search).get("stage");
    const title =
      path === "/"
        ? views[view]
        : path === "/sdlc" && Object.hasOwn(sdlcStages, selectedStage)
          ? sdlcStages[selectedStage]
          : titles[path];
    const heading = document.querySelector(".topbar h1");
    heading.textContent = title;
    document.title = `${title} — Auto Finance Quality`;
    const lifecyclePage = [
      "/",
      "/sdlc",
      "/project-dashboard",
      "/progress",
      "/quality-lifecycle",
      "/usage",
    ].includes(path);
    const lifecycleArea =
      path === "/"
        ? ["requirements", "stories"].includes(view)
          ? "BA"
          : "Testing"
        : ["/progress", "/quality-lifecycle"].includes(path)
          ? "Testing"
          : "";
    document.querySelector(".topbar .eyebrow").textContent = lifecyclePage
      ? `SDLC / ${lifecycleArea ? lifecycleArea + " / " : ""}${title}`
      : `${["/products", "/auto-finance-guide"].includes(path) ? "Auto finance" : "Workspace"} / ${title}`;
    displayedUrl = location.pathname + location.search;
    window.dispatchEvent(new CustomEvent("workspace-page-changed", { detail: { path, view } }));
    if (focus) {
      if (path === "/auto-finance-guide")
        document.getElementById("auto-finance-guide-frame").focus();
      else {
        heading.tabIndex = -1;
        heading.focus();
      }
      window.scrollTo(0, 0);
    }
  }
  window.navigateWorkspace = (url, focus = true) => {
    if (url === "/products") url = "/auto-finance-guide?section=products";
    if (url === "/" && window.roleHomePath) url = window.roleHomePath;
    if (window.roleCanNavigate && !window.roleCanNavigate(url)) return;
    if (
      location.pathname === "/sdlc" &&
      location.pathname + location.search !== url &&
      !window.dispatchEvent(new CustomEvent("sdlc-phase-changing", { cancelable: true }))
    )
      return;
    if (location.pathname + location.search !== url) history.pushState(null, "", url);
    showPage(focus);
  };
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a");
    if (
      !link ||
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      link.target ||
      link.origin !== location.origin ||
      !(link.pathname in titles) ||
      link.hash
    )
      return;
    event.preventDefault();
    window.navigateWorkspace(link.pathname + link.search);
  });
  window.addEventListener("popstate", () => {
    if (
      new URL(displayedUrl, location.origin).pathname === "/sdlc" &&
      displayedUrl !== location.pathname + location.search &&
      !window.dispatchEvent(new CustomEvent("sdlc-phase-changing", { cancelable: true }))
    ) {
      history.pushState(null, "", displayedUrl);
      return;
    }
    showPage(true);
  });
  document
    .querySelector(".topbar .top-actions")
    .prepend(document.getElementById("stop-generation"));
  const automation = document.getElementById("automation-workspace");
  ["feature-file-view", "step-definitions"].forEach((id) =>
    automation.append(document.getElementById(id)),
  );
  document
    .getElementById("automation-workspace-actions")
    .prepend(document.querySelector(".automation-language-control"));
  const syncAutomation = () => {
    const available = !document.getElementById("results").classList.contains("hidden");
    document.getElementById("automation-workspace-status").textContent = available
      ? `Active suite: ${document.getElementById("feature").textContent}. Review the selected test cases before building or downloading scripts.`
      : "Create test cases to build, inspect and download automation files.";
    document.querySelectorAll("[data-suite-action]").forEach((button) => {
      const original = document.getElementById(button.dataset.suiteAction);
      button.disabled =
        !available || original.disabled || original.getAttribute("aria-disabled") === "true";
    });
  };
  document.querySelectorAll("[data-suite-action]").forEach((button) => {
    button.addEventListener("click", () =>
      document.getElementById(button.dataset.suiteAction).click(),
    );
  });
  ["view-feature", "generate-step-definitions", "view-csharp-pack"].forEach((id) => {
    document.getElementById(id).addEventListener(
      "click",
      () => {
        if (document.body.dataset.qualityView !== "automation")
          window.navigateWorkspace("/?view=automation", false);
      },
      { capture: true },
    );
  });
  const observer = new MutationObserver(syncAutomation);
  observer.observe(document.getElementById("results"), {
    attributes: true,
    subtree: true,
    attributeFilter: ["disabled", "aria-disabled", "class"],
  });
  window.addEventListener("workspace-suite-rendered", syncAutomation);
  syncAutomation();
  showPage();
})();
