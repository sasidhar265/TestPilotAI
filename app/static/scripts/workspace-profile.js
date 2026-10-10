(() => {
  const $ = (id) => document.getElementById(id);
  const toggle = $("profile-toggle"),
    panel = $("profile-panel");
  function closeProfile() {
    panel.classList.add("hidden");
    toggle.setAttribute("aria-expanded", "false");
  }
  toggle.addEventListener("click", () => {
    const open = panel.classList.toggle("hidden") === false;
    toggle.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".profile-menu")) closeProfile();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.classList.contains("hidden")) {
      closeProfile();
      toggle.focus();
    }
  });
  async function loadUserProfile() {
    try {
      window.renderWorkspaceProfile(await window.loadWorkspaceProfile());
    } catch {
      $("profile-name").textContent = "Profile unavailable";
    }
  }
  loadUserProfile();
})();
