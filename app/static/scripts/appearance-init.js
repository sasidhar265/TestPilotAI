/* Start branding before the page shell can paint its built-in identity. */
(() => {
  document.documentElement.dataset.appearancePending = "true";
  document.title = "Loading workspace…";
  window.workspaceAppearanceTitleGuard = new MutationObserver(() => {
    if (!window.workspaceAppearance?.get() && document.title !== "Loading workspace…")
      document.title = "Loading workspace…";
  });
  window.workspaceAppearanceTitleGuard.observe(document.querySelector("title"), {
    childList: true, subtree: true, characterData: true,
  });
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  window.workspaceAppearanceRequest = fetch("/api/appearance", {
    cache: "no-store",
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok) throw new Error("Application settings are unavailable");
    return response.json();
  }).finally(() => clearTimeout(timeout));
  // The deferred appearance owner handles failures after the shell has been built.
  window.workspaceAppearanceRequest.catch(() => {});
})();
