/* Authentication precedes project choice; the server checks membership on every read. */
(() => {
  window.mountProjectPicker = (dialog, options = {}) => {
    const get = (id) => dialog.querySelector(`#${id}`);
    let account = null, busy = false, projects = [];
    let previousProject = null;
    const key = () => `sdlc-active-project:${account.username}`;
    function status(message, error = false) {
      get("selection-status").textContent = message;
      get("selection-status").dataset.error = String(error);
    }
    function setBusy(value) {
      busy = value;
      for (const id of ["project-choice", "project-name", "project-create-button", "selection-retry"])
        get(id).disabled = value;
      get("project-continue").disabled = value || !get("project-choice").value;
      get("project-cancel").disabled = value;
      get("project-selection").setAttribute("aria-busy", String(value));
      get("project-create").setAttribute("aria-busy", String(value));
    }
    async function api(path, body) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 20000);
      try {
        const response = await fetch(path, {
          method: body ? "POST" : "GET", signal: controller.signal,
          headers: { "Content-Type": "application/json" },
          ...(body ? { body: JSON.stringify(body) } : {}),
        });
        if (response.status === 401) {
          window.location.replace("/login?reason=expired");
          throw new Error("Your session expired. Sign in again to continue.");
        }
        const data = await response.json().catch(() => null);
        if (!response.ok) {
          const message = {
            403: "You no longer have access to this project or action. Reload the list or ask your administrator for access.",
            404: "This project is no longer available. Reload the list and choose another project.",
            409: "The project changed while you were working. Reload the list and try again.",
            422: "Enter a valid project name and try again.",
          }[response.status] || "The project service is unavailable. Try again shortly.";
          throw new Error(message);
        }
        if (!data) throw new Error("The project service returned an unreadable response. Retry loading projects.");
        return data;
      } catch (error) {
        if (error.name === "AbortError") throw new Error("Loading timed out. Check your connection and retry.");
        if (error instanceof TypeError) throw new Error("Unable to connect. Check your connection and retry.");
        throw error;
      } finally { clearTimeout(timer); }
    }
    async function load() {
      if (busy) return;
      setBusy(true);
      get("selection-retry").hidden = true;
      get("project-selection").hidden = true;
      get("project-empty").hidden = true;
      get("project-create-panel").hidden = true;
      status("Loading your projects…");
      try {
        account = await api("/api/auth/profile");
        if (!account.username || account.is_guest) {
          window.location.replace("/login");
          return;
        }
        get("selection-intro").textContent = `Signed in as ${account.display_name || account.username}. Choose a project to continue.`;
        projects = await api("/api/sdlc/projects");
        if (!Array.isArray(projects) || projects.some((item) => typeof item.id !== "string" || typeof item.name !== "string"))
          throw new Error("The project list could not be read. Retry loading projects.");
        try {
          const saved = sessionStorage.getItem(key());
          previousProject = projects.some((item) => item.id === saved) ? saved : null;
        } catch { previousProject = null; }
        get("project-cancel").hidden = !options.onCancel && !previousProject;
        get("project-choice").replaceChildren(new Option("Choose a project", ""),
          ...projects.map((project) => new Option(project.name, project.id)));
        get("project-selection").hidden = !projects.length;
        get("project-empty").hidden = Boolean(projects.length);
        const canCreate = ["admin", "test_lead", "ba", "functional_tester", "automation_tester", "non_functional_tester"].includes(account.role);
        get("project-create-panel").hidden = !canCreate;
        get("project-create-panel").open = canCreate && !projects.length;
        get("project-empty-help").textContent = canCreate
          ? "Create your first project below, or ask a project owner to add you to an existing project."
          : "Ask your administrator or project owner to add you to a project.";
        status(new URLSearchParams(location.search).get("reason") === "unavailable"
          ? "We could not reopen the previous workspace. Select an available project to try again." : "");
      } catch (error) {
        status(error.message, true);
        get("selection-intro").textContent = "We could not load your available projects.";
        get("selection-retry").hidden = false;
      } finally { setBusy(false); }
    }
    async function openProject(identifier) {
      // Do not trust a cached list or browser storage as proof of project membership.
      const snapshot = await api(`/api/sdlc/projects/${encodeURIComponent(identifier)}`);
      if (snapshot.project?.id !== identifier) throw new Error("The selected project could not be verified. Reload the list and try again.");
      try {
        if (sessionStorage.getItem(key()) !== identifier)
          sessionStorage.removeItem(`quality-workspace-draft:v1:${account.username}`);
        sessionStorage.setItem(key(), identifier);
      } catch {
        throw new Error("Your browser blocked session storage. Allow storage for this site and try again.");
      }
      status("Opening your workspace…");
      if (options.onSelect) await options.onSelect(snapshot.project);
      else window.location.replace("/sdlc");
    }
    get("project-choice").addEventListener("change", () => {
      get("project-continue").disabled = busy || !get("project-choice").value;
    });
    get("project-selection").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (busy || !get("project-choice").value) return;
      setBusy(true);
      get("selection-retry").hidden = true;
      status("Checking project access…");
      try { await openProject(get("project-choice").value); }
      catch (error) { status(error.message, true); get("selection-retry").hidden = false; }
      finally { setBusy(false); }
    });
    get("project-create").addEventListener("submit", async (event) => {
      event.preventDefault();
      if (busy) return;
      const name = get("project-name").value.trim();
      if (!name) {
        status("Enter a project name before continuing.", true);
        get("project-name").focus();
        return;
      }
      setBusy(true);
      status("Creating your project…");
      try {
        const project = await api("/api/sdlc/projects", { name });
        if (typeof project.id !== "string") throw new Error("The created project could not be read. Reload the list before trying again.");
        // Creation succeeded: offer the saved project even if opening it fails.
        get("project-choice").add(new Option(project.name || name, project.id));
        get("project-choice").value = project.id;
        get("project-selection").hidden = false;
        get("project-empty").hidden = true;
        get("project-name").value = "";
        await openProject(project.id);
      } catch (error) { status(error.message, true); get("selection-retry").hidden = false; }
      finally { setBusy(false); }
    });
    get("selection-retry").addEventListener("click", load);
    async function cancel() {
      if (busy) { status("Wait for the current request to finish before closing."); return; }
      if (options.onCancel) {
        options.onCancel();
        dialog.close();
      } else if (previousProject) {
        setBusy(true);
        try { await openProject(previousProject); }
        catch (error) { status(error.message, true); get("selection-retry").hidden = false; }
        finally { setBusy(false); }
      } else status("Choose a project to open your workspace, or sign out.");
    }
    get("project-cancel").hidden = !options.onCancel;
    get("project-cancel").addEventListener("click", cancel);
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); cancel(); });
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "Tab") {
        const focusable = [...dialog.querySelectorAll("button:not(:disabled), input:not(:disabled), select:not(:disabled), summary, a[href], [tabindex='0']")]
          .filter((node) => node.getClientRects().length && getComputedStyle(node).visibility !== "hidden");
        const first = focusable[0], last = focusable.at(-1);
        const outside = !focusable.includes(document.activeElement);
        if (!first) { event.preventDefault(); get("selection-title").focus(); }
        else if (event.shiftKey && (document.activeElement === first || outside)) {
          event.preventDefault(); last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || outside)) {
          event.preventDefault(); first.focus();
        }
      }
      if (event.key === "Escape" && dialog.querySelector(".theme-menu:not([hidden])")) {
        event.preventDefault();
        window.dispatchEvent(new Event("appearance-close"));
        get("theme-gear")?.focus();
      }
    });
    dialog.addEventListener("close", () => {
      document.body.classList.remove("project-picker-open");
      options.onClose?.();
    });
    get("project-signout").addEventListener("click", async () => {
      get("project-signout").disabled = true;
      try {
        await api("/api/auth/logout", {});
        window.workspaceSessionEnding = true;
        for (const storedKey of Object.keys(sessionStorage)) {
          if (storedKey.startsWith("sdlc-active-project:") || storedKey.startsWith("quality-workspace-draft:"))
            sessionStorage.removeItem(storedKey);
        }
        window.location.replace("/login");
      } catch (error) { status(error.message, true); get("project-signout").disabled = false; }
    });
    document.body.classList.add("project-picker-open");
    dialog.showModal();
    get("selection-title").focus();
    load();
  };
  if (document.body.classList.contains("project-selection-page"))
    window.mountProjectPicker(document.getElementById("project-picker"));
})();
