/* Keep the active suite and ongoing work alive across workspace pages. */
(() => {
  const titles = {
    "/project-dashboard": "Project dashboard",
    "/": "Build confidence in every vehicle finance quote.",
    "/progress": "Progress & execution",
    "/quality-lifecycle": "Quality Lifecycle",
  };
  function showPage(focus = false) {
    const path = location.pathname;
    document.querySelectorAll("[data-workspace-page]").forEach((page) => {
      page.hidden = page.dataset.workspacePage !== path;
    });
    document.querySelectorAll(".primary-nav a").forEach((link) => {
      const active = link.pathname === path;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    const heading = document.querySelector(".topbar h1");
    heading.textContent = titles[path];
    document.title = `${titles[path]} — Auto Finance Quality`;
    document.querySelector(".topbar .eyebrow").textContent =
      path === "/" ? "Automobile finance · Quality workspace" : "Workspace / " + titles[path];
    window.dispatchEvent(new CustomEvent("workspace-page-changed", { detail: { path } }));
    if (focus) {
      heading.tabIndex = -1;
      heading.focus();
      window.scrollTo(0, 0);
    }
  }
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
    history.pushState(null, "", link.pathname);
    showPage(true);
  });
  window.addEventListener("popstate", () => showPage(true));
  showPage();
})();
