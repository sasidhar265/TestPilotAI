/* Server-issued capabilities govern visible actions; APIs enforce the same permissions. */
(() => {
  let access = null;
  const unrestricted = {generation_targets: ["manual", "automation", "non_functional", "both"], stories: true, scenarios: true, test_cases: true, automation: true, non_functional: true, admin: true};
  const restrict = (element, allowed) => {
    if (element) element.toggleAttribute("data-role-hidden", !allowed);
  };
  const canNavigate = (url) => {
    if (!access) return true;
    const target = new URL(url, location.origin);
    const view = target.searchParams.get("view");
    if (target.pathname === "/admin/users") return access.admin;
    const stage = window.workflowStages.find(stage => stage.view === view);
    if (target.pathname === "/" && stage && !["requirements", "stories"].includes(view)) return access[stage.permission];
    if (["/quality-lifecycle", "/progress"].includes(target.pathname)) return access.test_cases;
    return true;
  };
  window.roleCanNavigate = canNavigate;
  function apply() {
    if (!access) return;
    document.querySelectorAll("[data-permission]").forEach(element => {
      const allowed = Boolean(access[element.dataset.permission]);
      restrict(element, allowed);
      if (element.classList.contains("admin-navigation")) element.hidden = !allowed;
    });
    document.querySelectorAll(".primary-nav a").forEach(link => restrict(link, canNavigate(link.href)));
    document.querySelectorAll("[data-workflow-step]").forEach(link => {
      restrict(link, canNavigate(link.href));
      if (document.body.dataset.role === "ba" && link.dataset.workflowStep === "requirements") link.href = "/?view=requirements";
    });
    window.workflowStages.slice(2).forEach((stage, index) => restrict(document.getElementById(`stage-tab-${index + 3}`), access[stage.permission]));
    restrict(document.getElementById("review-stories"), access.scenarios);
    restrict(document.getElementById("stage-scenarios"), access.scenarios);
    restrict(document.getElementById("stage-cases"), access.test_cases);
    document.querySelectorAll("[data-automation-control]").forEach(element => restrict(element, access.automation));
    ["open-script-pack", "script-pack-dialog"].forEach(id => restrict(document.getElementById(id), access.non_functional));
    document.querySelectorAll('[data-suite-action="open-script-pack"]').forEach(element => restrict(element, access.non_functional));
    restrict(document.getElementById("save-business-rules"), !["ba", "business_stakeholder", "product_owner", "developer", "release_manager"].includes(document.body.dataset.role));
    const target = document.getElementById("output-target");
    if (target) {
      const permitted = access.generation_targets;
      let changed = false;
      for (const option of [...target.options]) {
        if (!permitted.includes(option.value)) { option.remove(); changed = true; }
      }
      restrict(target.closest("fieldset"), permitted.length > 0);
      restrict(document.getElementById("manual-type-control"), permitted.length > 0);
      if (changed && permitted.length) { target.value = permitted[0]; target.dispatchEvent(new Event("change", {bubbles: true})); }
      // BA stories do not require a testing route; the request uses a neutral manual context.
      if (!permitted.length) target.append(new Option("Business analysis", "manual"));
    }
    document.querySelectorAll('[href="/admin/users"]').forEach(element => restrict(element, access.admin));
    if (!canNavigate(location.href) && window.navigateWorkspace) window.navigateWorkspace(access.home_path || "/", false);
    if (document.body.dataset.role === "ba") {
      document.querySelectorAll('.primary-nav a[href="/"]').forEach(link => { link.href = "/?view=requirements"; });
      document.querySelectorAll("a.brand").forEach(link => { link.href = access.home_path; });
    }
    document.body.removeAttribute("data-access-pending");
  }
  document.addEventListener("click", event => {
    const restricted = event.target.closest("[data-role-hidden]");
    const link = event.target.closest("a");
    if (restricted || (link && !canNavigate(link.href))) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  window.addEventListener("workspace-page-changed", apply);
  window.addEventListener("workspace-suite-rendered", apply);
  window.loadWorkspaceProfile().then(profile => {
    if (!profile) return;
    access = profile.capabilities || (profile.is_admin ? unrestricted : null);
    if (!access) return;
    document.body.dataset.role = profile.role || "admin";
    window.workspaceCapabilities = access;
    window.roleHomePath = access.home_path || "/";
    apply();
    window.dispatchEvent(new CustomEvent("workspace-role-ready", {detail: access}));
  }).catch(() => {});
})();
