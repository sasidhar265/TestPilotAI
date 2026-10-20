/* Agent delivery cockpit: server-owned jobs, durable events and real execution evidence. */
(() => {
  const el = (id) => document.getElementById(id);
  let baseline = null;
  let phase = null;
  let lifecycle = null;
  let clientError = null;
  let project = null,
    run = null,
    configuration = null,
    pollBusy = false,
    starting = false;
  const viewTabs = document.createElement("nav");
  viewTabs.className = "sdlc-progress-navigation";
  viewTabs.setAttribute("aria-label", "Workflow progress");
  viewTabs.innerHTML = '<a id="sdlc-view-progress">View progress →</a>';
  el("sdlc-content").prepend(viewTabs);
  const summary = document.createElement("aside");
  summary.className = "workflow-pipeline-summary";
  summary.setAttribute("aria-labelledby", "workflow-pipeline-heading");
  summary.innerHTML = '<h3 id="workflow-pipeline-heading">Application workflow</h3><p id="workflow-pipeline-status" role="status"></p><ol id="workflow-pipeline-agents" aria-label="Application workflow stages"></ol><p class="field-help">Workflow status follows human handoffs. AI run progress does not grant approval.</p>';
  const requirementsActivity = document.createElement("div");
  requirementsActivity.className = "requirements-agent-activity";
  requirementsActivity.append(document.querySelector(".agent-route-card"));
  summary.prepend(requirementsActivity);
  const workspace = document.querySelector(".sdlc-workspace");
  const workflowLayout = document.createElement("div");
  workflowLayout.className = "sdlc-workflow-layout";
  workspace.before(workflowLayout);
  workflowLayout.append(workspace, summary);
  const isOverview = () => new URLSearchParams(location.search).get("view") === "pipeline" &&
    !new URLSearchParams(location.search).has("phase") &&
    !new URLSearchParams(location.search).has("stage");
  const workflowStages = () => isOverview() || !phase ? null :
    phase.agent_stages.length ? phase.agent_stages : phase.id === "business-approval" ? ["requirements"] : [];
  const inScope = (stage) => workflowStages() === null || workflowStages().includes(stage);
  const agentStatus = (stage) => run?.completed?.includes(stage) ? "passed" :
    run?.stage === stage ? run.status : "waiting";
  const environmentStages = {
    repository: ["design", "development", "testing"], build: ["development", "testing"],
    preview: ["development"], staging: ["release", "operations"],
    production: ["release", "operations"], rollback: ["release", "operations"],
  };
  function updateView() {
    const params = new URLSearchParams(location.search);
    const pipeline = params.get("view") === "pipeline";
    const requestedReview = params.get("review");
    const review = phase?.id === "business-approval" && requestedReview
      ? `&review=${encodeURIComponent(requestedReview === "progress" ? "overview" : requestedReview)}` : "";
    const scopedUrl = `/sdlc?phase=${encodeURIComponent(phase?.id || "requirements")}${review}`;
    const requirementsWorkspace = location.pathname === "/sdlc" &&
      phase?.id === "requirements" && !pipeline;
    summary.setAttribute("aria-labelledby", requirementsWorkspace ? "agent-workflow-title" : "workflow-pipeline-heading");
    viewTabs.hidden = location.pathname !== "/sdlc" || params.get("view") === "documents" || phase?.id === "business-approval";
    summary.hidden = params.get("view") === "documents";
    workflowLayout.classList.toggle("pipeline-hidden", summary.hidden);
    el("sdlc-view-progress").href = pipeline ? scopedUrl : `${scopedUrl}&view=pipeline`;
    el("sdlc-view-progress").textContent = pipeline ? `← Back to ${phase?.label || "current stage"}` : "View progress →";
    el("sdlc-pipeline-overview").hidden = isOverview();
    el("sdlc-agent-tools").open = pipeline;
    el("sdlc-agent-tools").hidden = requirementsWorkspace;
    const scope = isOverview()
      ? "All delivery agents, recorded activity and evidence for the selected run."
      : `${phase?.label || "Current workflow"}: relevant agents, recorded activity and evidence. Stop and resume controls apply to the complete selected run.`;
    const source = run?.mission.requirements_version
      ? ` Requirements v${run.mission.requirements_version}; latest saved version: ${baseline?.version || "none"}.` : "";
    el("sdlc-pipeline-scope").textContent = scope + source;
    el("sdlc-environments").querySelectorAll("[data-environment]").forEach((item) => {
      item.hidden = !(environmentStages[item.dataset.environment] || []).some(inScope);
    });
    if (pipeline && location.pathname === "/sdlc") {
      const title = isOverview() ? "Delivery pipeline" : `${phase?.label || "Workflow"} · Delivery pipeline`;
      document.querySelector(".topbar h1").textContent = title;
      document.title = `${title} — Auto Finance Quality`;
      const navigation = el("sdlc-pipeline-link");
      if (isOverview()) { navigation.setAttribute("aria-current", "page"); navigation.classList.add("active"); }
    }
    const phases = configuration?.workflow?.phases || [];
    const stageDefinition = configuration?.workflow?.definition || [];
    const currentStage = stageDefinition.find((item) => item.id === lifecycle?.stage);
    const currentPhase = phases.find((item) => item.id === lifecycle?.phase);
    el("workflow-pipeline-status").textContent = clientError || (currentPhase
      ? `Current stage: ${currentPhase.label}${currentStage ? ` · ${currentStage.label}` : ""}${lifecycle.pending_approval ? " · Human approval required" : ""}`
      : "Prepare and save requirements to begin the workflow.");
    const currentIndex = phases.findIndex((item) => item.id === lifecycle?.phase);
    el("workflow-pipeline-agents").replaceChildren(...phases.map((item, index) => {
      const entry = document.createElement("li");
      entry.dataset.phase = item.id;
      const link = document.createElement("a");
      link.href = `/sdlc?phase=${encodeURIComponent(item.id)}`;
      const number = cardText("span", String(index + 1).padStart(2, "0"), "pipeline-phase-number");
      number.setAttribute("aria-hidden", "true");
      const copy = document.createElement("span");
      const status = !lifecycle ? "Awaiting workflow status" : item.id === lifecycle.phase
        ? lifecycle.stage === "closed" ? "Release closed" : lifecycle.pending_approval
          ? "Human approval required" : "Current workflow"
        : index < currentIndex ? "Earlier workflow" : "Upcoming";
      copy.append(cardText("strong", item.label), cardText("small", status));
      if (item.id === lifecycle?.phase && currentStage) {
        copy.append(cardText("small", `Active step: ${currentStage.label}`));
        if (currentStage.roles?.length)
          copy.append(cardText("small", `Owner: ${currentStage.roles.map((role) => role.replaceAll("_", " ")).join(", ")}`));
      }
      link.title = item.description;
      if (item.id === phase?.id && !isOverview()) {
        link.setAttribute("aria-current", "page");
        const stages = item.agent_stages.length ? item.agent_stages : ["requirements"];
        for (const agent of configuration.agents.filter((agent) => stages.includes(agent.stage)))
          copy.append(cardText("small", `AI · ${agent.name}: ${agentStatus(agent.stage)}`, "pipeline-agent-status"));
      }
      if (item.id === lifecycle?.phase) entry.dataset.current = "true";
      link.append(number, copy);
      entry.append(link);
      return entry;
    }));
    if (!configuration) el("workflow-pipeline-status").textContent = clientError || "Loading delivery agents…";
  }
  const active = (value) => ["queued", "running", "cancelling"].includes(value?.status);
  async function api(path, body) {
    const response = await fetch(`/api/sdlc${path}`, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(
        typeof result.detail === "string" ? result.detail : "Check the mission inputs and retry.",
      );
    return result;
  }
  function error(message) {
    clientError = message;
    el("sdlc-run-error").hidden = !message;
    el("sdlc-run-error").textContent = message || "";
    updateView();
  }
  function cardText(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function render() {
    updateView();
    const board = el("sdlc-agent-grid");
    board.replaceChildren();
    for (const [index, agent] of (configuration?.agents || []).entries()) {
      const state = agentStatus(agent.stage);
      const card = document.createElement("article");
      card.className = `sdlc-agent-card ${state}`;
      card.dataset.stage = agent.stage;
      card.hidden = !inScope(agent.stage);
      card.append(
        cardText(
          "span",
          `${String(index + 1).padStart(2, "0")} · ${state.replaceAll("_", " ")}`,
          "sdlc-agent-state",
        ),
        cardText("h4", agent.name),
        cardText("p", agent.role),
      );
      const specialists = document.createElement("div");
      specialists.className = "sdlc-specialists";
      agent.specialists.forEach((name) => specialists.append(cardText("span", name)));
      card.append(specialists);
      const content = run?.artifacts?.[agent.stage];
      if (content) {
        const inspect = document.createElement("details");
        inspect.append(cardText("summary", "Inspect agent output"));
        inspect.append(
          cardText("pre", content.document || content.summary || JSON.stringify(content, null, 2)),
        );
        card.append(inspect);
      }
      board.append(card);
    }
    el("sdlc-run-status").textContent = run
      ? `${run.status} · ${run.action && run.action !== "idle" ? run.action : "target: " + run.mission.target}`
      : "Waiting for Requirements";
    el("sdlc-source-summary").textContent = run?.mission.requirements_version
      ? `This run uses Requirements v${run.mission.requirements_version}. Latest saved baseline: v${baseline?.version || "none"}.${baseline && baseline.version !== run.mission.requirements_version ? " Requirements changed; start a new run to regenerate downstream outputs." : ""}`
      : baseline
        ? `Requirements v${baseline.version} · ${baseline.content.document.slice(0, 240)}`
        : "Save Requirements to begin the lifecycle.";
    el("sdlc-run-status").dataset.status = run?.status || "ready";
    el("sdlc-cancel-run").disabled = !active(run) || run?.status === "cancelling";
    el("sdlc-resume-run").hidden = !["blocked", "failed", "interrupted"].includes(run?.status);
    el("sdlc-resume-run").disabled = Boolean(
      run?.mission.requirements_version && baseline?.version !== run.mission.requirements_version,
    );
    el("sdlc-resume-run").title = el("sdlc-resume-run").disabled
      ? "Requirements changed. Start a new run from Requirements."
      : "Continue from the failed gate";
    el("sdlc-bundle").hidden = !run || active(run);
    if (run) el("sdlc-bundle").href = `/api/sdlc/runs/${run.id}/bundle`;
    const options = el("sdlc-target").options;
    for (const option of options)
      option.disabled = document.body.dataset.role === "ba" && option.value !== "design";
    el("sdlc-run-error").hidden = !(run?.error || clientError);
    el("sdlc-run-error").textContent = run?.error || clientError || "";
    const activity = el("sdlc-run-events");
    activity.replaceChildren();
    for (const event of (run?.events || []).filter((event) => inScope(event.stage)).slice(-40).reverse()) {
      const item = document.createElement("li");
      item.className = event.status;
      item.append(
        cardText("strong", event.stage.toUpperCase()),
        cardText("p", event.message),
        cardText("small", `${event.status} · ${new Date(event.created_at).toLocaleTimeString()}`),
      );
      activity.append(item);
    }
    if (!activity.children.length)
      activity.append(cardText("li", "Agents will record their actions and gate decisions here."));
    const evidence = el("sdlc-run-evidence");
    evidence.replaceChildren();
    const development = run?.artifacts?.development,
      testing = run?.artifacts?.testing,
      release = run?.artifacts?.release,
      operations = run?.artifacts?.operations;
    const rows = [];
    if (development && inScope("development"))
      rows.push(
        ["Candidate revision", development.revision],
        ["Changed files", String(development.files.length)],
        ["Build", `Exit ${development.build.exit_code}`],
        ["Independent review", development.review.passed ? "Passed" : "Failed"],
      );
    if (testing && inScope("testing"))
      rows.push(
        [
          "Generated BDD execution",
          `${testing.execution.passed} passed · ${testing.execution.failed} failed · ${testing.execution.skipped} not executed`,
        ],
        ["Execution scope", testing.execution.scope],
      );
    if (release && inScope("release"))
      rows.push(
        ["Promoted environment", release.environment],
        ["Staging receipt", release.staging.receipt.deployment_id],
      );
    if (release?.production && inScope("release")) rows.push(["PROD receipt", release.production.receipt.deployment_id]);
    if (operations && inScope("operations"))
      rows.push([
        "Service verification",
        `${operations.health.status} · ${operations.environment}`,
      ]);
    const list = document.createElement("dl");
    list.className = "sdlc-evidence";
    rows.forEach(([label, value]) => {
      const item = document.createElement("div");
      item.append(cardText("dt", label), cardText("dd", value));
      list.append(item);
    });
    evidence.append(list);
    const tasks = Object.entries(run?.artifacts || {}).filter(([stage]) => inScope(stage))
      .flatMap(([, value]) => value.tasks || []);
    if (tasks.length) {
      evidence.append(cardText("h4", "Agent work breakdown"));
      const list = document.createElement("ul");
      tasks.forEach((task) =>
        list.append(
          cardText("li", `${task.id} · ${task.title} · ${task.acceptance_criteria.join("; ")}`),
        ),
      );
      evidence.append(list);
    }
    if (run?.blocking_evidence && inScope(run.stage)) {
      const details = document.createElement("details");
      details.append(
        cardText("summary", "Blocking evidence"),
        cardText("pre", JSON.stringify(run.blocking_evidence, null, 2)),
      );
      evidence.append(details);
    }
    if (!rows.length && !tasks.length)
      evidence.append(cardText("p", "Evidence is populated by actual agent and tool results."));
  }
  async function showRun(identifier) {
    clientError = null;
    run = identifier ? await api(`/runs/${identifier}`) : null;
    render();
  }
  window.addEventListener("sdlc-project-loaded", async (event) => {
    if (project?.id !== event.detail?.project?.id) lifecycle = null;
    project = event.detail?.project || null;
    baseline = event.detail?.artifacts?.find((item) => item.stage === "requirements-input") || null;
    el("sdlc-source-summary").textContent = baseline
      ? `Requirements v${baseline.version} · ${baseline.content.document.slice(0, 240)}`
      : "Save Requirements to begin the lifecycle.";
    const runs = event.detail?.runs || [];
    el("sdlc-runs").replaceChildren(new Option("Select a delivery run", ""));
    runs.forEach((item) =>
      el("sdlc-runs").add(
        new Option(
          `${item.status} · ${item.mission.target} · ${new Date(item.created_at).toLocaleString()}`,
          item.id,
        ),
      ),
    );
    if (project && runs.some((item) => item.id === run?.id)) el("sdlc-runs").value = run.id;
    else el("sdlc-runs").value = runs[0]?.id || "";
    try {
      await showRun(el("sdlc-runs").value);
    } catch (issue) {
      error(issue.message);
    }
  });
  window.addEventListener("sdlc-phase-selected", (event) => {
    phase = event.detail.phase;
    render();
  });
  window.addEventListener("sdlc-lifecycle-loaded", (event) => {
    lifecycle = event.detail?.state || null;
    updateView();
  });
  window.addEventListener("workspace-page-changed", render);
  el("sdlc-runs").onchange = () =>
    showRun(el("sdlc-runs").value).catch((issue) => error(issue.message));
  async function saveRequirements() {
    if (!project) throw new Error("Select or create a project in Requirements first.");
    if (window.testingWorkspaceBusy())
      throw new Error("Wait for the current requirements action to finish.");
    const source = await window.prepareSdlcRequirements();
    const saved = await api(`/projects/${project.id}/artifacts/requirements-input`, {
      content: { source_request: source },
      base_version: baseline?.version || 0,
      links: [],
    });
    await window.sdlcSaveWorkflow?.();
    await window.sdlcRefreshProject();
    el("sdlc-requirements-status").textContent =
      `Requirements v${saved.version} saved. All stages will consume this baseline.`;
    return saved;
  }
  async function submit(start) {
    if (starting) return;
    starting = true;
    render();
    try {
      const saved = await saveRequirements();
      if (start) {
        run = await api(`/projects/${project.id}/runs`, {
          requirements_version: saved.version,
          target: el("sdlc-target").value,
        });
        await window.sdlcRefreshProject();
        window.navigateWorkspace("/sdlc");
      }
    } catch (issue) {
      el("sdlc-requirements-status").textContent = issue.message;
      error(issue.message);
    } finally {
      starting = false;
      render();
    }
  }
  window.startRequirementsDelivery = () => submit(true);
  el("sdlc-cancel-run").onclick = async () => {
    try {
      run = await api(`/runs/${run.id}/cancel`, {});
      render();
    } catch (issue) {
      error(issue.message);
    }
  };
  el("sdlc-resume-run").onclick = async () => {
    try {
      run = await api(`/runs/${run.id}/resume`, {});
      render();
    } catch (issue) {
      error(issue.message);
    }
  };
  async function poll() {
    if (!active(run) || pollBusy) return;
    pollBusy = true;
    try {
      const identifier = run.id;
      const updated = await api(`/runs/${identifier}`);
      if (run?.id !== identifier) return;
      run = updated;
      render();
      if (!active(run)) await window.sdlcRefreshProject();
    } catch (issue) {
      error(issue.message);
    } finally {
      pollBusy = false;
    }
  }
  setInterval(poll, 2500);
  window
    .loadWorkspaceProfile()
    .then((profile) =>
      profile.is_guest || document.body.dataset.guest === "true" ? null : api("/agents"),
    )
    .then((value) => {
      if (!value) return;
      configuration = value;
      if (value.workflow) window.dispatchEvent(new CustomEvent("sdlc-policy-loaded", { detail: value.workflow }));
      const environments = el("sdlc-environments");
      environments.replaceChildren();
      for (const [name, ready] of Object.entries(value.configured)) {
        const item = cardText(
            "span",
            `${name}: ${ready ? "connected" : "configuration required"}`,
            ready ? "connected" : "missing",
          );
        item.dataset.environment = name;
        environments.append(item);
      }
      render();
    })
    .catch((issue) => error(issue.message));
  const initial = window.sdlcCurrentProject?.();
  if (initial) window.sdlcRefreshProject();
})();
