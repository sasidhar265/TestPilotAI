document.addEventListener("DOMContentLoaded", async () => {
  const $ = (id) => document.getElementById(id);
  let state = { profiles: [], selection: { profile: "", revision: 0 } };
  let admin = false,
    editing = null;
  async function api(path, method = "GET", body) {
    const response = await fetch(path, {
      method,
      cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string" ? data.detail : "Check the profile fields and try again.",
      );
    return data;
  }
  function updateChoice() {
    const selected = state.profiles.find(
      (profile) => profile.id === $("domain-profile-choice").value,
    );
    $("domain-profile-description").textContent = selected?.description || "";
    $("edit-domain-profile").disabled = !admin || !selected || selected.builtin;
  }
  async function load() {
    state = await api("/api/domain-profiles");
    $("domain-profile-choice").replaceChildren(
      ...state.profiles.map(
        (profile) =>
          new Option(`${profile.name}${profile.builtin ? " · Built-in" : ""}`, profile.id),
      ),
    );
    $("domain-profile-choice").value = state.selection.profile;
    $("domain-profile-choice").disabled = !admin;
    $("apply-domain-profile").disabled = !admin;
    $("new-domain-profile").disabled = !admin;
    updateChoice();
  }
  function edit(profile = null) {
    editing = profile;
    const form = $("domain-profile-form");
    form.reset();
    for (const key of ["id", "name", "description", "instructions"])
      form.elements[key].value = profile?.[key] || "";
    form.elements.id.readOnly = Boolean(profile);
    form.elements.baseline.value = JSON.stringify(profile?.baseline || { sources: [] }, null, 2);
    $("domain-profile-editor-title").textContent = profile
      ? "Edit domain profile"
      : "Create domain profile";
    $("domain-profile-editor-status").textContent =
      profile && profile.id === state.selection.profile
        ? "Saving this active profile updates guidance for new requests."
        : "Save the profile, then select Apply profile to activate it.";
    $("domain-profile-editor").showModal();
  }
  $("domain-profile-choice").addEventListener("change", updateChoice);
  $("new-domain-profile").addEventListener("click", () => edit());
  $("edit-domain-profile").addEventListener("click", () =>
    edit(state.profiles.find((profile) => profile.id === $("domain-profile-choice").value)),
  );
  for (const id of ["close-domain-profile", "cancel-domain-profile"])
    $(id).addEventListener("click", () => $("domain-profile-editor").close());
  $("apply-domain-profile").addEventListener("click", async () => {
    $("apply-domain-profile").disabled = true;
    try {
      await api("/api/admin/domain-profiles/selection", "PUT", {
        profile: $("domain-profile-choice").value,
        expected_revision: state.selection.revision,
      });
      await load();
      window.dispatchEvent(new Event("workspace-domain-changed"));
      try {
        sessionStorage.removeItem("finance-reference-calculation");
      } catch {}
      $("domain-profile-status").textContent =
        `Applied ${state.selection.profile}. New requests use this profile. Reopen the workspace to start with fresh drafts.`;
    } catch (error) {
      $("domain-profile-status").textContent = error.message;
    } finally {
      $("apply-domain-profile").disabled = !admin;
    }
  });
  $("domain-profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!admin) return;
    const form = event.currentTarget;
    const payload = {};
    for (const key of ["id", "name", "description", "instructions", "review_note"])
      payload[key] = form.elements[key].value.trim();
    try {
      payload.baseline = JSON.parse(form.elements.baseline.value);
    } catch {
      $("domain-profile-editor-status").textContent = "Business baseline must contain valid JSON.";
      return;
    }
    payload.confirmed = form.elements.confirmed.checked;
    payload.expected_revision = editing?.revision || 0;
    const submit = form.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      const saved = await api("/api/admin/domain-profiles", "POST", payload);
      await load();
      $("domain-profile-choice").value = saved.id;
      updateChoice();
      $("domain-profile-editor").close();
      $("domain-profile-status").textContent =
        saved.id === state.selection.profile
          ? "Active profile updated for new requests."
          : "Profile saved. Select Apply profile to activate it.";
    } catch (error) {
      $("domain-profile-editor-status").textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
  try {
    admin = Boolean((await window.loadWorkspaceProfile()).is_admin);
    await load();
    $("domain-profile-status").textContent =
      `Active profile: ${state.selection.profile}${admin ? "" : " · Administrator access is required to change profiles."}`;
  } catch (error) {
    $("domain-profile-status").textContent = error.message;
  }
});
