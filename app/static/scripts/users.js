const roleLabels = {
  business_stakeholder: "Business stakeholder",
  product_owner: "Product owner / Scrum master",
  developer: "Developer",
  release_manager: "Release manager / DevOps",
  ba: "Business analyst",
  functional_tester: "Functional tester",
  automation_tester: "Automation tester",
  non_functional_tester: "Non-functional tester",
  test_lead: "Test lead",
  admin: "Admin",
};
const status = document.getElementById("users-status"),
  list = document.getElementById("users-list"),
  form = document.getElementById("create-user");
const roleDescriptions = {
  ba: "Reviews requirements and clarifications before stakeholder approval.",
  business_stakeholder:
    "Approves business requirements and records user acceptance testing decisions.",
  product_owner:
    "Refines the backlog, sets priorities and estimates, and plans sprint assignments.",
  developer: "Implements assigned stories, records development evidence, and resolves defects.",
  functional_tester:
    "Designs and executes manual tests, records defects, and retests fixes. The QA lead owns final sign-off.",
  automation_tester:
    "Creates and runs automation, records test evidence, and retests fixes. The QA lead owns final sign-off.",
  non_functional_tester:
    "Reviews performance and database testing using the available specialist tools.",
  test_lead:
    "Coordinates QA and records QA sign-off. Business and release approvals have separate accountable owners.",
  release_manager:
    "Reviews release readiness and owns staging validation, production approval, and deployment handoffs.",
  admin:
    "Manages accounts and can perform stage-owner actions. Human evidence and approval gates still apply.",
};
function describeRole() {
  document.getElementById("role-help").textContent =
    roleDescriptions[form.elements.role.value] || "Select a role to see its responsibilities.";
}
form.elements.role.addEventListener("change", describeRole);
describeRole();
let currentUsername = "";
async function request(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string" ? body.detail : "Check the entered account details.",
    );
  return body;
}
async function loadUsers() {
  const users = await request("/api/admin/users");
  list.replaceChildren();
  document.getElementById("user-count").textContent =
    `${users.length} account${users.length === 1 ? "" : "s"}`;
  for (const user of users) {
    const row = document.createElement("tr");
    for (const value of [user.display_name, user.username]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    const roleCell = document.createElement("td");
    const roleBadge = document.createElement("span");
    roleBadge.className = "user-role";
    roleBadge.textContent = roleLabels[user.role] || user.role;
    roleCell.append(roleBadge);
    row.append(roleCell);
    const accessCell = document.createElement("td");
    const accessBadge = document.createElement("span");
    accessBadge.className = `user-access ${user.enabled ? "enabled" : "disabled"}`;
    accessBadge.textContent = user.enabled ? "Enabled" : "Disabled";
    accessCell.append(accessBadge);
    row.append(accessCell);
    const actions = document.createElement("td");
    if (user.managed && user.username.toLowerCase() !== currentUsername.toLowerCase()) {
      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "secondary edit-user";
      edit.setAttribute("aria-label", `Edit ${user.username}`);
      edit.title = `Edit ${user.username}`;
      edit.innerHTML =
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="m16 3 5 5-12 12-6 1 1-6Z"/><path d="m14 5 5 5"/></svg>';
      edit.onclick = () => {
        if (!saving) editUser(user);
      };
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "secondary delete-user";
      remove.setAttribute("aria-label", `Delete ${user.username}`);
      remove.title = `Delete ${user.username}`;
      remove.innerHTML =
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg>';
      remove.onclick = async () => {
        if (
          saving ||
          !window.confirm(
            `Delete ${user.display_name} (${user.username})? Their account and application access will be removed.`,
          )
        )
          return;
        saving = true;
        remove.disabled = edit.disabled = true;
        for (const element of form.elements) element.disabled = true;
        try {
          await request(`/api/admin/users/${encodeURIComponent(user.username)}`, {
            method: "DELETE",
          });
          if (editingUsername === user.username) resetEditor();
          status.textContent = `Deleted ${user.username}. Application access has been removed.`;
          await loadUsers();
        } catch (error) {
          status.textContent = error.message;
          remove.disabled = edit.disabled = false;
        } finally {
          saving = false;
          for (const element of form.elements) element.disabled = false;
        }
      };
      const controls = document.createElement("div");
      controls.className = "user-row-actions";
      controls.append(edit, remove);
      actions.append(controls);
    } else actions.textContent = user.managed ? "Your account" : "Initial admin";
    row.append(actions);
    list.append(row);
  }
}
let editingUsername = null,
  saving = false;
const submitButton = document.getElementById("save-user"),
  cancelEdit = document.getElementById("cancel-edit");
function resetEditor() {
  editingUsername = null;
  form.reset();
  form.elements.username.readOnly = false;
  describeRole();
  form.elements.password.required = true;
  document.getElementById("create-title").textContent = "Create user";
  document.getElementById("password-help").textContent =
    "At least 12 characters. Share with the user securely.";
  submitButton.textContent = "Create user";
  cancelEdit.classList.add("hidden");
}
function editUser(user) {
  resetEditor();
  editingUsername = user.username;
  const parts = user.display_name.split(" ");
  form.elements.first_name.value = user.first_name ?? parts.shift();
  form.elements.last_name.value = user.last_name ?? parts.join(" ");
  form.elements.username.value = user.username;
  form.elements.username.readOnly = true;
  form.elements.role.value = user.role;
  describeRole();
  form.elements.enabled.value = String(Boolean(user.enabled));
  form.elements.password.required = false;
  document.getElementById("password-help").textContent =
    "Leave blank to keep the current password, or enter a new password of at least 12 characters.";
  document.getElementById("create-title").textContent = `Edit user · ${user.username}`;
  submitButton.textContent = "Update user";
  cancelEdit.classList.remove("hidden");
  status.textContent = `Editing ${user.username}. Username cannot be changed.`;
  form.scrollIntoView({
    block: "center",
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
  });
  form.elements.first_name.focus({ preventScroll: true });
}
cancelEdit.onclick = () => {
  if (!saving) {
    resetEditor();
    status.textContent = "Editing cancelled.";
  }
};
form.onsubmit = async (event) => {
  event.preventDefault();
  if (saving) return;
  const username = editingUsername;
  const data = Object.fromEntries(new FormData(form));
  data.enabled = data.enabled === "true";
  if (username) {
    delete data.username;
    if (!data.password) delete data.password;
  }
  saving = true;
  for (const element of form.elements) element.disabled = true;
  try {
    const user = await request(
      username ? `/api/admin/users/${encodeURIComponent(username)}` : "/api/admin/users",
      {
        method: username ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      },
    );
    resetEditor();
    status.textContent = `${username ? "Updated" : "Created"} ${user.username} as ${user.role}. Access is ${user.enabled ? "enabled" : "disabled"}.${username ? " Existing sessions revoked." : ""}`;
    await loadUsers();
  } catch (error) {
    status.textContent = error.message;
  } finally {
    saving = false;
    for (const element of form.elements) element.disabled = false;
  }
};
(async () => {
  try {
    const profile = await window.loadWorkspaceProfile();
    currentUsername = profile.username;
    window.renderWorkspaceProfile(profile);
    await loadUsers();
  } catch (error) {
    status.textContent = error.message;
    form.querySelector("button").disabled = true;
  }
})();

const profileToggle = document.getElementById("profile-toggle"),
  profilePanel = document.getElementById("profile-panel");
function closeProfile() {
  profilePanel.classList.add("hidden");
  profileToggle.setAttribute("aria-expanded", "false");
}
profileToggle.onclick = () => {
  const open = profilePanel.classList.toggle("hidden") === false;
  profileToggle.setAttribute("aria-expanded", String(open));
};
document.addEventListener("click", (event) => {
  if (!event.target.closest(".profile-menu")) closeProfile();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !profilePanel.classList.contains("hidden")) {
    closeProfile();
    profileToggle.focus();
  }
});
