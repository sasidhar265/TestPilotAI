/* Persistent SDLC records share the existing quality workspace without changing its gates. */
(() => {
  const byId = (id) => document.getElementById(id);
  const stages = {
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
  const projectLink = document.createElement("a");
  projectLink.href = "/sdlc";
  projectLink.className = "button secondary";
  projectLink.textContent = "SDLC projects";
  document.querySelector(".topbar .top-actions").prepend(projectLink);
  const status = (value) => {
    byId("sdlc-status").textContent = value;
    projectLink.title = value;
    if (/unable|newer|failed|reload|denied|permit/i.test(value))
      projectLink.textContent = "SDLC · save needs attention";
  };
  const latest = (name) => snapshot?.artifacts.find((item) => item.stage === name);
  const projectKey = () => `sdlc-active-project:${account}`;
  async function api(path, payload) {
    const response = await fetch(`/api/sdlc${path}`, {
      method: payload ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Unable to save. Check the required fields.",
      );
    return data;
  }
  async function work(action) {
    if (pending) return;
    pending = true;
    byId("sdlc-create").querySelector('button[type="submit"]').disabled = true;
    byId("sdlc-project").disabled = true;
    try {
      await action();
    } catch (error) {
      status(error.message);
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
    projectLink.textContent = snapshot ? `Project: ${snapshot.project.name}` : "SDLC projects";
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
    byId("sdlc-document").value = artifact?.content.document || "";
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
      text.textContent = item.content.document || "Saved testing workspace snapshot";
      details.append(text);
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
    if (identifier) localStorage.setItem(projectKey(), identifier);
    if (!sameProject) workflowReady = false;
    autosaveBlocked = false;
    render();
  }
  async function refreshProjects(preferred) {
    const projects = await api("/projects");
    const select = byId("sdlc-project");
    select.replaceChildren(new Option("Select a project", ""));
    projects.forEach((project) => select.add(new Option(project.name, project.id)));
    const chosen = preferred || localStorage.getItem(projectKey());
    select.value = projects.some((project) => project.id === chosen) ? chosen : "";
    await load(select.value);
    if (snapshot && latest("workflow")) {
      window.restoreTestingWorkspace(latest("workflow").content);
      workflowReady = true;
    }
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
      window.navigateWorkspace(`/sdlc?stage=${name}`, false);
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
  function selectRouteStage(focus = false) {
    if (location.pathname !== "/sdlc") return;
    const requested = new URLSearchParams(location.search).get("stage");
    if (!requested || !Object.hasOwn(stages, requested)) return;
    if (stage !== requested) {
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
    if (!pending) work(() => window.sdlcSaveWorkflow());
  }, 5000);
  window
    .loadWorkspaceProfile()
    .then((profile) => {
      account = profile.username || "local";
      if (profile.is_guest) {
        projectLink.hidden = true;
        document.querySelector('.primary-nav a[href="/sdlc"]').hidden = true;
      } else work(() => refreshProjects());
    })
    .catch((error) => status(error.message));
})();
