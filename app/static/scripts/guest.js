(() => {
  if (document.body.dataset.guest !== "true") return;
  const workspace = document.querySelector('[data-workspace-page="/"]');
  const blockedControl = 'input, textarea, select, button:not([data-stage])';
  function restrictControls() {
    workspace.querySelectorAll(blockedControl).forEach((control) => {
      if (!control.disabled) control.disabled = true;
      control.title = "Sign in to make changes. Guest access is view-only.";
    });
    document.querySelectorAll('a[href]').forEach((link) => {
      if (link.origin !== location.origin || ["/", "/progress", "/login"].includes(link.pathname)
          || link.pathname.startsWith("/api/automation/reports/")) return;
      link.hidden = true;
      link.style.display = "none";
    });
  }
  restrictControls();
  new MutationObserver(restrictControls).observe(workspace, {
    childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"],
  });
  document.addEventListener("submit", (event) => {
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);
  document.addEventListener("click", (event) => {
    const control = event.target.closest("button, a");
    if (!control) return;
    const forbiddenAction = workspace.contains(control) && control.matches(blockedControl);
    const forbiddenLink = control.matches("a[href]") && control.origin === location.origin
      && !["/", "/progress", "/login"].includes(control.pathname)
      && !control.pathname.startsWith("/api/automation/reports/");
    if (forbiddenAction || forbiddenLink) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
})();
