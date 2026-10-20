/* Persistent SDLC records share the existing quality workspace without changing its gates. */
(() => {
  document.documentElement.dataset.projectContext = "pending";
  const byId = (id) => document.getElementById(id);
  const stages = {
    "requirements-input": [
      "Saved BRD",
      "Read or download the exact saved BRD baseline. BA business reports and metrics are available under BA review & approval → Business documents.",
      "",
    ],
    planning: [
      "Planning",
      "Inspect the agent-produced outcomes, scope, milestones, dependencies and risks.",
      "# Project plan\n\n## Outcome and success measures\n\n## Scope and exclusions\n\n## Owners and stakeholders\n\n## Milestones and dependencies\n\n## Risks and mitigations\n\n## Open questions\n",
    ],
    requirements: [
      "Business analysis",
      "Inspect the BA assessment and stories generated from the saved Requirements baseline.",
      "# Requirements baseline\n\n## Business needs\n\n## Functional requirements\n\n## Non-functional requirements\n\n## Acceptance criteria\n\n## Source documents and open questions\n",
    ],
    design: [
      "Design",
      "Review the architecture, interfaces, data model and decisions before development.",
      "# Design review\n\n## Linked requirements\n\n## Components and responsibilities\n\n## API contracts\n\n## Data model and migrations\n\n## Security and privacy\n\n## Alternatives and decisions\n\n## Review questions\n",
    ],
    development: [
      "Development",
      "Inspect the agent implementation, repository evidence, build and independent review.",
      "# Implementation record\n\n## Linked design versions\n\n## Work items and owners\n\n## Code changes and pull requests\n\n## Code review findings\n\n## Validation evidence\n\n## Outstanding work\n",
    ],
    testing: [
      "Testing",
      "The existing testing capabilities remain available; workspace snapshots are versioned with your project.",
      "# Test readiness\n\n## Scope and coverage\n\n## Test cycle and suite references\n\n## Execution evidence\n\n## Defects and residual risks\n",
    ],
    release: [
      "Release",
      "Prepare a release decision grounded in reviewed artifacts, test evidence and rollback instructions.",
      "# Release readiness\n\n## Target version and commit\n\n## Environment and release owner\n\n## Test evidence and known issues\n\n## Deployment procedure\n\n## Rollback procedure\n\n## Go/no-go decision\n",
    ],
    operations: [
      "Operations",
      "Maintain the operational handover, service checks, incident records and follow-up work.",
      "# Operations handover\n\n## Service owners and support contacts\n\n## Health checks and alerting\n\n## Runbooks\n\n## Incidents and impact\n\n## Recovery evidence\n\n## Maintenance backlog\n",
    ],
  };
  let snapshot = null,
    stage = Object.hasOwn(stages, new URLSearchParams(location.search).get("stage"))
      ? new URLSearchParams(location.search).get("stage")
      : "planning",
    repository = null,
    pending = false;
  let dirty = false,
    account = "local",
    workflowReady = false,
    autosaveBlocked = false;
  const emptyWorkspace = structuredClone(window.exportTestingWorkspace());
  const emptyDocument = document.createElement("p");
  emptyDocument.id = "sdlc-document-empty";
  emptyDocument.setAttribute("role", "status");
  byId("sdlc-document").after(emptyDocument);
  const artifactText = item => item.content.document || item.content.source_request?.description ||
    JSON.stringify(item.content, null, 2);
  const projectLink = document.createElement("a");
  projectLink.href = "/select-project";
  projectLink.className = "profile-link";
  projectLink.textContent = "Change project";
  document.getElementById("logout").before(projectLink);
  const workspaceError = document.createElement("p");
  workspaceError.className = "workspace-save-error";
  workspaceError.setAttribute("role", "alert");
  workspaceError.hidden = true;
  document.querySelector(".topbar").after(workspaceError);
  let pickerAssets = null;
  function loadPickerAssets() {
    if (pickerAssets) return pickerAssets;
    let timeout;
    const deadline = new Promise((resolve, reject) => {
      timeout = setTimeout(() => reject(new DOMException("Project selection timed out", "TimeoutError")), 20000);
    });
    const requests = Promise.all([
      new Promise((resolve, reject) => {
        const style = document.createElement("link");
        style.rel = "stylesheet";
        style.href = "/static/styles/project-selection.css?v=20261019-project-dialog";
        style.onload = resolve;
        style.onerror = () => { style.remove(); reject(new Error("Unable to load project selection. Retry Change project.")); };
        document.head.append(style);
      }),
      window.mountProjectPicker ? Promise.resolve() : new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "/static/scripts/project-selection.js?v=20261020-session-cleanup";
        script.onload = resolve;
        script.onerror = () => { script.remove(); reject(new Error("Unable to load project selection. Retry Change project.")); };
        document.body.append(script);
      }),
    ]);
    pickerAssets = Promise.race([requests, deadline]).finally(() => clearTimeout(timeout))
      .catch((error) => { pickerAssets = null; throw error; });
    return pickerAssets;
  }
  projectLink.addEventListener("click", async (event) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    if (projectLink.getAttribute("aria-disabled") === "true") return;
    if (!window.dispatchEvent(new CustomEvent("sdlc-phase-changing", { cancelable: true }))) {
      workspaceError.textContent = "Finish or save your current work before changing projects.";
      workspaceError.hidden = false;
      return;
    }
    workspaceError.hidden = true;
    projectLink.setAttribute("aria-disabled", "true");
    try {
      const response = await fetch("/select-project", { signal: AbortSignal.timeout(20000) });
      if (response.status === 401 || new URL(response.url).pathname === "/login") {
        window.location.replace("/login?reason=expired");
        return;
      }
      if (!response.ok) throw new Error("Unable to load project selection. Retry Change project.");
      const content = new DOMParser().parseFromString(await response.text(), "text/html");
      const picker = content.getElementById("project-picker");
      if (!picker) throw new Error("Project selection could not be loaded. Refresh the page and try again.");
      picker.querySelectorAll("[data-picker-standalone]").forEach((node) => node.remove());
      await loadPickerAssets();
      document.body.append(picker);
      document.getElementById("profile-panel").classList.add("hidden");
      document.getElementById("profile-toggle").setAttribute("aria-expanded", "false");
      window.mountProjectPicker(picker, {
        onCancel: () => {},
        onClose: () => {
          picker.remove();
          projectLink.removeAttribute("aria-disabled");
          document.getElementById("profile-toggle").focus();
        },
        onSelect: (selected) => {
          if (selected.id === snapshot?.project.id) { picker.close(); return; }
          // The departing workspace must not restore its draft into the newly selected project.
          window.projectContextSwitching = true;
          window.location.replace("/sdlc");
        },
      });
    } catch (error) {
      projectLink.removeAttribute("aria-disabled");
      document.getElementById("project-picker")?.remove();
      document.body.classList.remove("project-picker-open");
      workspaceError.textContent = error.name === "TimeoutError"
        ? "Loading project selection timed out. Check your connection and retry."
        : error instanceof TypeError ? "Unable to load project selection. Check your connection and retry Change project."
        : error.message;
      workspaceError.hidden = false;
    }
  });
  const status = (value) => {
    byId("sdlc-status").textContent = value;
    projectLink.title = value;
  };
  const latest = (name) => snapshot?.artifacts.find((item) => item.stage === name);
  const projectKey = () => `sdlc-active-project:${account}`;
  async function api(path, payload) {
    const response = await fetch(`/api/sdlc${path}`, {
      method: payload ? "POST" : "GET",
      signal: AbortSignal.timeout(20000),
      headers: { "Content-Type": "application/json" },
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) window.location.replace("/login?reason=expired");
    if (!response.ok) {
      const error = new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Unable to save. Check the required fields.",
      );
      error.status = response.status;
      throw error;
    }
    return data;
  }
  async function work(action, background = false) {
    if (pending) return;
    pending = true;
    if (!background) workspaceError.hidden = true;
    byId("sdlc-create").querySelector('button[type="submit"]').disabled = true;
    byId("sdlc-project").disabled = true;
    try {
      await action();
    } catch (error) {
      status(error.message);
      workspaceError.textContent = error.name === "TimeoutError"
        ? "The request timed out. Retry your action when the connection is available."
        : error.message;
      workspaceError.hidden = false;
      if (snapshot && [403, 404].includes(error.status)) {
        sessionStorage.removeItem(projectKey());
        byId("sdlc-content").inert = true;
        window.location.replace("/select-project?reason=unavailable");
      }
    } finally {
      pending = false;
      byId("sdlc-create").querySelector('button[type="submit"]').disabled = false;
      byId("sdlc-project").disabled = false;
    }
  }
  function render() {
    byId("sdlc-content").hidden = false;
    document.querySelector(".sdlc-artifact-ledger").hidden = !snapshot;
    const createPanel = byId("sdlc-create-panel");
    const projectId = snapshot?.project.id || "";
    if (createPanel.dataset.project !== projectId) {
      createPanel.open = !snapshot;
      createPanel.dataset.project = projectId;
    }
    if (!snapshot) {
      window.dispatchEvent(new CustomEvent("sdlc-project-loaded", { detail: null }));
      return;
    }
    const role = document.body.dataset.role || "admin";
    const allowed =
      ["admin", "test_lead"].includes(role) ||
      (role === "ba" && ["planning", "requirements", "design"].includes(stage)) ||
      (["functional_tester", "automation_tester", "non_functional_tester"].includes(role) &&
        stage === "testing");
    byId("sdlc-document").readOnly = true;
    ["sdlc-save", "sdlc-template", "sdlc-read-repository"].forEach((id) => {
      byId(id).disabled = id !== "sdlc-read-repository" || !allowed;
    });
    byId("sdlc-links").disabled = true;
    const artifact = latest(stage);
    byId("sdlc-stage-title").textContent = stages[stage][0];
    byId("sdlc-stage-help").textContent = stages[stage][1];
    byId("sdlc-document").value = artifact ? artifactText(artifact) : "";
    byId("sdlc-document").hidden = !artifact;
    emptyDocument.hidden = Boolean(artifact);
    emptyDocument.textContent = `No ${stages[stage][0].toLowerCase()} document has been saved for this project. This archive shows saved outputs only; opening it does not generate a document.`;
    repository = artifact?.content.repository || null;
    byId("sdlc-repository-evidence").textContent = repository
      ? JSON.stringify(repository, null, 2)
      : "";
    const reviews = snapshot.reviews.filter(
      (item) => item.stage === stage && item.version === artifact?.version,
    );
    byId("sdlc-version").textContent = artifact
      ? `Version ${artifact.version} · ${reviews.at(-1)?.decision.replaceAll("_", " ") || "Review required"}`
      : "No saved version";
    byId("sdlc-testing").hidden = stage !== "testing";
    byId("sdlc-repository").hidden = stage !== "development";
    byId("sdlc-restore-workflow").disabled = !latest("workflow");
    ["sdlc-approve", "sdlc-changes"].forEach((id) => {
      byId(id).disabled = !artifact || !["admin", "test_lead"].includes(role);
    });
    byId("sdlc-review-comment").value = "";
    document.querySelectorAll("[data-sdlc-stage]").forEach((button) => {
      if (button.dataset.sdlcStage === stage) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    const links = byId("sdlc-links");
    links.replaceChildren();
    for (const link of artifact?.links || []) {
      const label =
        link.stage === "requirements-input"
          ? "Requirements baseline"
          : stages[link.stage]?.[0] || link.stage;
      const changed = latest(link.stage)?.version !== link.version;
      links.add(
        new Option(
          `${label} · v${link.version}${changed ? " · newer source available" : ""}`,
          `${link.stage}:${link.version}`,
          false,
          true,
        ),
      );
    }
    const history = byId("sdlc-history");
    history.replaceChildren();
    for (const item of snapshot.artifacts.filter(
      (item) => item.stage === stage || (stage === "testing" && item.stage === "workflow"),
    )) {
      const details = document.createElement("details");
      details.className = "sdlc-history-item";
      const summary = document.createElement("summary");
      summary.textContent = `${item.stage} v${item.version} · ${item.author} · ${new Date(item.created_at).toLocaleString()}`;
      details.append(summary);
      const text = document.createElement("pre");
      text.textContent = artifactText(item);
      details.append(text);
      const download = document.createElement("button");
      download.type = "button";
      download.className = "secondary";
      download.textContent = `Download ${stages[item.stage]?.[0] || item.stage} v${item.version}`;
      download.onclick = () => {
        const plainText = Boolean(item.content.document || item.content.source_request?.description);
        const url = URL.createObjectURL(new Blob([artifactText(item)], {
          type: plainText ? "text/plain;charset=utf-8" : "application/json",
        }));
        const link = document.createElement("a");
        link.href = url;
        link.download = `${item.stage}-v${item.version}.${plainText ? "txt" : "json"}`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      };
      details.append(download);
      for (const link of item.links) {
        const p = document.createElement("p");
        p.textContent = `Depends on ${link.stage} v${link.version}${latest(link.stage)?.version !== link.version ? " · newer source available; review impact" : ""}`;
        details.append(p);
      }
      for (const review of snapshot.reviews.filter(
        (review) => review.stage === item.stage && review.version === item.version,
      )) {
        const p = document.createElement("p");
        p.textContent = `${review.decision.replaceAll("_", " ")} · ${review.reviewer} · ${review.comment}`;
        details.append(p);
      }
      history.append(details);
    }
    if (!history.children.length) history.textContent = `No saved versions for ${stages[stage][0].toLowerCase()} yet.`;
    dirty = false;
    window.dispatchEvent(new CustomEvent("sdlc-project-loaded", { detail: snapshot }));
  }
  window.sdlcRefreshProject = () => load(snapshot?.project.id);
  window.sdlcCurrentProject = () => snapshot?.project;
  async function load(identifier) {
    if (snapshot?.project.id !== identifier && window.projectRecordDraftPending?.()) {
      byId("sdlc-project").value = snapshot?.project.id || "";
      throw new Error("Save or clear the record draft before switching projects.");
    }
    const sameProject = snapshot?.project.id === identifier;
    snapshot = identifier ? await api(`/projects/${identifier}`) : null;
    if (identifier) sessionStorage.setItem(projectKey(), identifier);
    if (!sameProject) workflowReady = false;
    autosaveBlocked = false;
    render();
  }
  async function refreshProjects(preferred) {
    const projects = await api("/projects");
    const select = byId("sdlc-project");
    select.replaceChildren(new Option("Select a project", ""));
    projects.forEach((project) => select.add(new Option(project.name, project.id)));
    const chosen = preferred || sessionStorage.getItem(projectKey());
    select.value = projects.some((project) => project.id === chosen) ? chosen : "";
    if (!select.value) {
      sessionStorage.removeItem(projectKey());
      window.location.replace(chosen ? "/select-project?reason=unavailable" : "/select-project");
      return;
    }
    await load(select.value);
    // Browser drafts recover navigation within this login. Saved project history
    // is restored only through the explicit Restore action, never on sign-in.
  }
  window.sdlcSelectProject = refreshProjects;
  const nav = document.querySelector(".sdlc-stages");
  for (const [name, value] of Object.entries(stages)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.dataset.sdlcStage = name;
    button.textContent = value[0];
    button.onclick = () => {
      if (dirty) {
        status("Save your document before switching stages.");
        return;
      }
      const archive = new URLSearchParams(location.search).get("view") === "documents";
      window.navigateWorkspace(`/sdlc?${archive ? "view=documents&" : ""}stage=${name}`, false);
    };
    nav.append(button);
  }
  byId("sdlc-document").oninput = () => {
    dirty = true;
  };
  byId("sdlc-links").onchange = () => {
    dirty = true;
  };
  byId("sdlc-project").onchange = () =>
    work(async () => {
      if (dirty) {
        byId("sdlc-project").value = snapshot.project.id;
        throw new Error("Save your document before switching projects.");
      }
      if (window.testingWorkspaceBusy())
        throw new Error("Wait for generation to finish before switching projects.");
      await load(byId("sdlc-project").value);
      if (snapshot) {
        window.restoreTestingWorkspace(latest("workflow")?.content || emptyWorkspace);
        workflowReady = true;
      }
      status("Project loaded.");
    });
  byId("sdlc-create").onsubmit = (event) => {
    event.preventDefault();
    work(async () => {
      if (dirty || window.projectRecordDraftPending?.())
        throw new Error("Save or clear your current draft before creating a project.");
      const project = await api("/projects", { name: byId("sdlc-name").value });
      byId("sdlc-name").value = "";
      await refreshProjects(project.id);
      workflowReady = true;
      await window.sdlcSaveWorkflow();
      status("Project created.");
    });
  };
  byId("sdlc-template").onclick = () => {
    if (byId("sdlc-document").value.trim()) {
      status("Clear the editor before inserting a template. Saved history remains available.");
      return;
    }
    byId("sdlc-document").value = stages[stage][2];
    dirty = true;
  };
  byId("sdlc-read-repository").onclick = () =>
    work(async () => {
      repository = await api("/repository");
      byId("sdlc-repository-evidence").textContent = JSON.stringify(repository, null, 2);
      status(
        "Current repository evidence loaded. Versioned implementation evidence is produced by the Development Agent.",
      );
    });
  async function saveArtifact(name, content, links = []) {
    await api(`/projects/${snapshot.project.id}/artifacts/${name}`, {
      content,
      base_version: latest(name)?.version || 0,
      links,
    });
    const identifier = snapshot.project.id;
    snapshot = await api(`/projects/${identifier}`);
  }
  byId("sdlc-save").onclick = () =>
    work(async () => {
      const document = byId("sdlc-document").value.trim();
      if (!document) throw new Error("Enter a stage document before saving.");
      const links = [...byId("sdlc-links").selectedOptions].map((option) => {
        const [stage, version] = option.value.split(":");
        return { stage, version: Number(version) };
      });
      await saveArtifact(
        stage,
        { document, ...(stage === "development" && repository ? { repository } : {}) },
        links,
      );
      render();
      status("New version saved. Review is required for this version.");
    });
  for (const [id, decision] of [
    ["sdlc-approve", "approved"],
    ["sdlc-changes", "changes_requested"],
  ])
    byId(id).onclick = () =>
      work(async () => {
        if (dirty) throw new Error("Save your edits before reviewing.");
        const comment = byId("sdlc-review-comment").value.trim();
        if (!comment) throw new Error("Enter a review comment.");
        await api(`/projects/${snapshot.project.id}/artifacts/${stage}/reviews`, {
          version: latest(stage).version,
          decision,
          comment,
        });
        const identifier = snapshot.project.id;
        snapshot = await api(`/projects/${identifier}`);
        render();
        status("Review recorded for this version.");
      });
  byId("sdlc-save-workflow").onclick = () =>
    work(async () => {
      if (dirty) throw new Error("Save the stage document first.");
      await saveArtifact("workflow", window.exportTestingWorkspace());
      workflowReady = true;
      render();
      status("Testing workspace saved to this project.");
    });
  byId("sdlc-restore-workflow").onclick = () =>
    work(async () => {
      window.restoreTestingWorkspace(latest("workflow").content);
      workflowReady = true;
      window.navigateWorkspace("/?view=requirements");
      status("Testing workspace restored.");
    });
  window.sdlcSaveWorkflow = async () => {
    if (!snapshot || !workflowReady || autosaveBlocked || window.testingWorkspaceBusy()) return;
    const content = window.exportTestingWorkspace();
    if (JSON.stringify(latest("workflow")?.content) === JSON.stringify(content)) return;
    try {
      await saveArtifact("workflow", content);
    } catch (error) {
      autosaveBlocked = true;
      throw error;
    }
    status("Testing workspace saved to your active project.");
  };
  window.persistReviewedRequirements = async () => {
    if (!snapshot) throw new Error("Select or create a project above before continuing to Business approval.");
    if (pending || window.testingWorkspaceBusy()) throw new Error("Wait for the current action to finish.");
    const source = await window.prepareReviewedRequirements();
    const existing = latest("requirements-input")?.content.source_request;
    if (!existing || Object.keys(source).some((key) => JSON.stringify(source[key]) !== JSON.stringify(existing[key]))) {
      await saveArtifact("requirements-input", { source_request: source });
    }
    workflowReady = true;
    await window.sdlcSaveWorkflow();
    render();
    window.dispatchEvent(new Event("lifecycle-updated"));
    return latest("requirements-input");
  };
  function selectRouteStage(focus = false) {
    if (location.pathname !== "/sdlc") return;
    let requested = new URLSearchParams(location.search).get("stage");
    const documentsView = new URLSearchParams(location.search).get("view") === "documents";
    if (documentsView && !requested) requested = "requirements-input";
    if (!documentsView && (!requested || !Object.hasOwn(stages, requested))) return;
    if (requested && Object.hasOwn(stages, requested) && stage !== requested) {
      stage = requested;
      render();
    }
    const ledger = document.querySelector(".sdlc-artifact-ledger");
    if (snapshot) {
      ledger.open = true;
      if (focus) requestAnimationFrame(() => ledger.scrollIntoView({ block: "start" }));
    }
  }
  window.addEventListener("workspace-page-changed", (event) => {
    if (event.detail.path === "/sdlc") {
      selectRouteStage(true);
      if (!snapshot) work(() => refreshProjects());
    }
  });
  window.addEventListener("sdlc-project-loaded", () => selectRouteStage());
  document.addEventListener(
    "click",
    (event) => {
      const link = event.target.closest("a[href]");
      if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = new URL(link.href);
      if (
        dirty &&
        target.origin === location.origin &&
        target.pathname === "/sdlc" &&
        target.searchParams.get("stage") &&
        target.searchParams.get("stage") !== stage
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
        status("Save your stage document before switching stages.");
      }
    },
    true,
  );
  setInterval(() => {
    if (!pending && snapshot) work(() => window.sdlcSaveWorkflow(), true);
  }, 5000);
  window
    .loadWorkspaceProfile()
    .then((profile) => {
      account = profile.username || "local";
      if (profile.is_guest) {
        document.documentElement.dataset.projectContext = "ready";
        projectLink.hidden = true;
        document.querySelector('.primary-nav a[href="/sdlc"]').hidden = true;
      } else work(async () => {
        try {
          await refreshProjects();
          if (snapshot) document.documentElement.dataset.projectContext = "ready";
        } catch (error) {
          if (error.status === 401) return;
          if ([403, 404].includes(error.status)) sessionStorage.removeItem(projectKey());
          window.location.replace("/select-project?reason=unavailable");
        }
      });
    })
    .catch((error) => window.location.replace(error.status === 401
      ? "/login?reason=expired" : "/select-project?reason=unavailable"));
})();
