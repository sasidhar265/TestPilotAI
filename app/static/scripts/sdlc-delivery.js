/* Agent delivery cockpit: server-owned jobs, durable events and real execution evidence. */
(() => {
  const el = (id) => document.getElementById(id);
  let baseline = null;
  let lastRunView = null;
  let clientError = null;
  let project = null,
    run = null,
    configuration = null,
    pollBusy = false,
    starting = false;
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
  }
  function cardText(tag, text, className) {
    const node = document.createElement(tag);
    node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function render() {
    const signature = run ? `${run.id}:${run.status}` : null;
    if (signature && signature !== lastRunView)
      document.getElementById("sdlc-agent-tools").open = true;
    lastRunView = signature;
    if (configuration?.workflow)
      window.dispatchEvent(
        new CustomEvent("sdlc-policy-loaded", { detail: configuration.workflow }),
      );
    const board = el("sdlc-agent-grid");
    board.replaceChildren();
    for (const [index, agent] of (configuration?.agents || []).entries()) {
      const state = run?.completed?.includes(agent.stage)
        ? "passed"
        : run?.stage === agent.stage
          ? run.status
          : "waiting";
      const card = document.createElement("article");
      card.className = `sdlc-agent-card ${state}`;
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
    el("sdlc-start-delivery").disabled =
      !project ||
      active(run) ||
      starting ||
      !["admin", "test_lead", "ba"].includes(document.body.dataset.role || "admin");
    el("sdlc-save-requirements").disabled =
      !project ||
      active(run) ||
      starting ||
      !["admin", "test_lead", "ba"].includes(document.body.dataset.role || "admin");
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
    for (const event of (run?.events || []).slice(-40).reverse()) {
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
    if (development)
      rows.push(
        ["Candidate revision", development.revision],
        ["Changed files", String(development.files.length)],
        ["Build", `Exit ${development.build.exit_code}`],
        ["Independent review", development.review.passed ? "Passed" : "Failed"],
      );
    if (testing)
      rows.push(
        [
          "Generated BDD execution",
          `${testing.execution.passed} passed · ${testing.execution.failed} failed · ${testing.execution.skipped} not executed`,
        ],
        ["Execution scope", testing.execution.scope],
      );
    if (release)
      rows.push(
        ["Promoted environment", release.environment],
        ["Staging receipt", release.staging.receipt.deployment_id],
      );
    if (release?.production) rows.push(["PROD receipt", release.production.receipt.deployment_id]);
    if (operations)
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
    const tasks = Object.values(run?.artifacts || {}).flatMap((value) => value.tasks || []);
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
    if (run?.blocking_evidence) {
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
  el("sdlc-save-requirements").onclick = () => submit(false);
  el("sdlc-start-delivery").onclick = () => submit(true);
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
      const environments = el("sdlc-environments");
      environments.replaceChildren();
      for (const [name, ready] of Object.entries(value.configured))
        environments.append(
          cardText(
            "span",
            `${name}: ${ready ? "connected" : "configuration required"}`,
            ready ? "connected" : "missing",
          ),
        );
      render();
    })
    .catch((issue) => error(issue.message));
  const initial = window.sdlcCurrentProject?.();
  if (initial) window.sdlcRefreshProject();
})();
