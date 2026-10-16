/* Page orientation shared by full-page navigation and the existing SPA shell. */
(() => {
  const main = document.querySelector("main");
  const header = main?.querySelector(".topbar");
  const heading = header?.querySelector("h1");
  if (!heading) return;
  if (!main.id) main.id = "workspace-main-content";
  const skip = document.createElement("a");
  skip.href = `#${main.id}`;
  skip.className = "workspace-skip-link";
  skip.textContent = "Skip to main content";
  skip.onclick = () => {
    main.tabIndex = -1;
    main.focus();
  };
  document.body.prepend(skip);
  const breadcrumbs = document.createElement("nav");
  breadcrumbs.className = "workspace-breadcrumbs";
  breadcrumbs.setAttribute("aria-label", "Breadcrumb");
  heading.parentElement.prepend(breadcrumbs);
  let intro = header.querySelector(".page-intro, .users-intro");
  const suppliedIntro = Boolean(intro);
  if (!intro) {
    intro = document.createElement("p");
    intro.className = "page-intro";
    heading.after(intro);
  }
  const descriptions = {
    "/": "Start with a project and its requirements. Save a version, review the analysis, then follow the delivery workflow.",
    "/?view=stories":
      "Turn reviewed requirements into stories with clear acceptance criteria before creating tests.",
    "/?view=scenarios":
      "Review the behaviours to test and their requirement links before generating test cases.",
    "/?view=test-cases":
      "Review generated tests, resolve findings, and approve the cases you want to use.",
    "/?view=automation": "Inspect and download automation files for your approved test cases.",
    "/?view=execution": "Run approved tests and inspect recorded execution results and failures.",
    "/sdlc":
      "Choose a project, add your requirements, and follow the next action shown below.",
    "/project-dashboard":
      "See current project stages, pending decisions, and the work that needs your attention.",
    "/progress": "Review recorded test runs, failures, and execution reports.",
    "/quality-lifecycle": "Follow requirements through tests, execution results, and defects.",
    "/usage": "Review AI activity, provider usage, and recorded execution history.",
    "/logs": "Find application errors and inspect the events related to a request.",
    "/docs":
      "Explore API contracts and request examples. Calls use your current account permissions.",
    "/documentation":
      "Find application guidance, workflow explanations, and technical reference material.",
    "/static/user-guide.html":
      "Follow the steps from requirements to reviewed tests and execution results.",
  };
  function render() {
    const list = document.createElement("ol");
    const homeItem = document.createElement("li");
    const home = document.createElement("a");
    home.href = "/project-dashboard";
    home.textContent = "Workspace";
    homeItem.append(home);
    const current = document.createElement("li");
    current.textContent = heading.textContent;
    current.setAttribute("aria-current", "page");
    list.append(homeItem, current);
    breadcrumbs.replaceChildren(list);
    if (!suppliedIntro) {
      const view = new URLSearchParams(location.search).get("view");
      intro.textContent =
        descriptions[`${location.pathname}?view=${view}`] ||
        descriptions[location.pathname] ||
        "Review the information below and choose the action for your role.";
    }
  }
  window.addEventListener("workspace-page-changed", render);
  window.addEventListener("popstate", render);
  new MutationObserver(render).observe(heading, {
    childList: true,
    characterData: true,
    subtree: true,
  });
  render();
})();
