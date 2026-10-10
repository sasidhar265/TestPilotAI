/* One profile request per page, shared by account displays and access controls. */
(() => {
  let profileRequest;
  window.loadWorkspaceProfile = () => profileRequest ||= fetch("/api/auth/profile").then(response => {
    if (!response.ok) throw new Error("Profile unavailable");
    return response.json();
  });
  window.renderWorkspaceProfile = profile => {
    const element = id => document.getElementById(id);
    const adminIcon = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6z"/><circle cx="12" cy="10" r="2.5"/><path d="M8 16c0-4 8-4 8 0"/></svg>';
    for (const id of ["profile-toggle", "profile-avatar"]) {
      if (!element(id)) continue;
      if (profile.is_admin) element(id).innerHTML = adminIcon;
      else element(id).textContent = profile.initials;
    }
    element("manage-users")?.classList.toggle("hidden", !profile.is_admin);
    element("profile-name").textContent = profile.display_name;
    element("profile-role").textContent = profile.is_guest ? "Guest · View only" : profile.is_admin ? "Administrator" : (profile.capabilities?.role_label || "Workspace account");
    element("profile-toggle").setAttribute("aria-label", `Open profile menu for ${profile.display_name}${profile.is_admin ? " (Administrator)" : ""}`);
  };
})();
