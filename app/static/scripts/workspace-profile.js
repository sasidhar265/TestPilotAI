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
      const response = await fetch("/api/auth/profile");
      if (!response.ok) throw new Error("Profile unavailable");
      const profile = await response.json();
      const adminIcon =
        '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6z"/><circle cx="12" cy="10" r="2.5"/><path d="M8 16c0-4 8-4 8 0"/></svg>';
      for (const id of ["profile-toggle", "profile-avatar"]) {
        if (profile.is_admin) $(id).innerHTML = adminIcon;
        else $(id).textContent = profile.initials;
      }
      $("manage-users").classList.toggle("hidden", !profile.is_admin);
      $("profile-name").textContent = profile.display_name;
      $("profile-role").textContent = profile.is_admin ? "Administrator" : "Workspace account";
      $("profile-toggle").setAttribute(
        "aria-label",
        `Open profile menu for ${profile.display_name}${profile.is_admin ? " (Administrator)" : ""}`,
      );
    } catch {
      $("profile-name").textContent = "Profile unavailable";
    }
  }
  loadUserProfile();
})();
