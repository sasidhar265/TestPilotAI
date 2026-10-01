/* Project information comes from saved lifecycle records. */
(() => {
  if (document.body.dataset.guest === "true") return;
  const get = (id) => document.getElementById(id);
  let snapshot;
  let loading = false;
  const date = (value) => (value ? new Date(value).toLocaleString() : "Not recorded");
  const badge = (status) => `<span class="pm-badge">${esc(status || "Not recorded")}</span>`;
  const empty = (columns, message) =>
    `<tr><td colspan="${columns}" class="pm-empty">${esc(message)}</td></tr>`;
  function render() {
    if (!snapshot) return;
    const project = get("pm-project").value;
    const scoped = (kind) => snapshot[kind].filter((item) => item.project === project);
    const versions = scoped("requirements");
    const latest = new Map();
    for (const item of versions) {
      if (!latest.has(item.key) || item.version > latest.get(item.key).version)
        latest.set(item.key, item);
    }
    const requirements = [...latest.values()].sort((a, b) => a.key.localeCompare(b.key));
    const baselines = scoped("baselines");
    const suites = scoped("suites");
    const cycles = scoped("cycles");
    const cycleIds = new Set(cycles.map((item) => item.id));
    const defects = snapshot.defects.filter((item) => cycleIds.has(item.cycle_id));
    const attempts = snapshot.attempts.filter((item) => cycleIds.has(item.cycle_id));
    const openDefects = defects.filter((item) => !["resolved", "closed"].includes(item.status));
    const suiteIds = new Set(suites.map((item) => item.id));
    const impacts = snapshot.impacts.filter((item) => suiteIds.has(item.suite_id));
    const records = [...versions, ...baselines, ...suites, ...cycles, ...defects, ...attempts];
    const ids = new Set(records.map((item) => item.id));
    const activity = snapshot.audit.filter((item) => ids.has(item.record_id));
    const timestamps = [...records, ...activity]
      .map((item) => item.created_at)
      .filter(Boolean)
      .sort();
    const owners = [...new Set(requirements.map((item) => item.owner).filter(Boolean))];
    get("pm-project-title").textContent = project || "Your project at a glance";
    get("pm-project-summary").textContent = project
      ? "Requirements, ownership and delivery records for this project."
      : "Save your first project requirement in Quality lifecycle to build this overview.";
    get("pm-project-details").innerHTML = [
      ["Project ID", project || "No projects yet"],
      ["Requirement owners", owners.join(", ") || "Not recorded"],
      ["First recorded", date(timestamps[0])],
      ["Last activity", date(timestamps.at(-1))],
    ]
      .map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`)
      .join("");
    const metric = (label, value, hint) =>
      `<article class="pm-card"><span>${esc(label)}</span><strong>${value}</strong><small>${esc(hint)}</small></article>`;
    get("pm-metrics").innerHTML =
      metric("Requirements", requirements.length, "Latest version of each requirement") +
      metric(
        "Approved requirements",
        requirements.filter((r) => r.status === "approved").length,
        "Reviewed project scope",
      ) +
      metric("Delivery cycles", cycles.length, "Saved build and environment assignments") +
      metric("Open defects", openDefects.length, "Open, in progress or reopened");
    get("pm-baselines").innerHTML = baselines.length
      ? baselines
          .map(
            (item) =>
              `<li><strong>${esc(item.name)}</strong> ${badge(item.status)}<small>${item.requirements.length} requirements · ${esc(date(item.created_at))}</small></li>`,
          )
          .join("")
      : '<li class="pm-empty">No baselines saved. Group reviewed requirements in Quality lifecycle.</li>';
    const attention = [];
    const pending = requirements.filter((r) => r.status !== "approved").length;
    if (pending) attention.push(`${pending} requirements need review or approval.`);
    const flagged = requirements.filter((r) => r.quality_flags?.length).length;
    if (flagged) attention.push(`${flagged} requirements have quality flags to resolve.`);
    if (impacts.length)
      attention.push(
        `${impacts.length} requirement changes affect saved test suites. Review change impact in Quality lifecycle.`,
      );
    if (openDefects.length)
      attention.push(`${openDefects.length} unresolved defects need follow-up.`);
    if (requirements.length && !baselines.length)
      attention.push("Create a baseline to capture the agreed project scope.");
    if (!attention.length)
      attention.push(
        project
          ? "No outstanding items in the recorded project indicators."
          : "Add a requirement with a project ID, owner and source to get started.",
      );
    get("pm-attention").innerHTML = attention.map((value) => `<li>${esc(value)}</li>`).join("");
    const query = get("pm-search").value.trim().toLowerCase();
    const filtered = requirements.filter((r) =>
      [r.key, r.title, r.owner, r.source].join(" ").toLowerCase().includes(query),
    );
    get("pm-requirement-count").textContent =
      `${filtered.length} of ${requirements.length} requirements`;
    get("pm-requirements").innerHTML = filtered.length
      ? filtered
          .map(
            (r) =>
              `<tr><th scope="row">${esc(r.key)}<small>Version ${r.version}</small></th><td><strong>${esc(r.title)}</strong><details><summary>Scope and acceptance criteria</summary><p>${esc(r.description)}</p><ul>${(r.acceptance_criteria || []).map((value) => `<li>${esc(value)}</li>`).join("") || "<li>No acceptance criteria recorded.</li>"}</ul></details></td><td>${esc(r.owner)}</td><td>${esc(r.source)}</td><td>${badge(r.status)}</td></tr>`,
          )
          .join("")
      : empty(
          5,
          query ? "No requirements match your search." : "No requirements saved for this project.",
        );
    get("pm-cycles").innerHTML = cycles.length
      ? cycles
          .map(
            (c) =>
              `<tr><th scope="row">${esc(c.name)}</th><td>${esc(c.build)}</td><td>${esc(c.environment)}</td><td>${esc([...new Set(Object.values(c.assignments))].join(", "))}</td><td>${esc(date(c.created_at))}</td></tr>`,
          )
          .join("")
      : empty(5, "No delivery cycles saved for this project.");
  }
  async function refresh() {
    if (loading) return;
    loading = true;
    get("pm-refresh").disabled = true;
    get("pm-content").hidden = true;
    get("pm-status").textContent = "Loading project information…";
    try {
      const response = await fetch("/api/stlc", { signal: AbortSignal.timeout(15000) });
      if (!response.ok)
        throw new Error("Project information could not be loaded. Refresh to retry.");
      const data = await response.json();
      if (
        ![
          "requirements",
          "baselines",
          "suites",
          "cycles",
          "defects",
          "attempts",
          "audit",
          "impacts",
        ].every((key) => Array.isArray(data[key]))
      )
        throw new Error("Project information is unavailable. Refresh to retry.");
      snapshot = data;
      const selection = get("pm-project").value;
      const projects = [
        ...new Set(
          [...data.requirements, ...data.baselines, ...data.suites, ...data.cycles].map(
            (r) => r.project,
          ),
        ),
      ].sort();
      get("pm-project").replaceChildren(
        ...(projects.length
          ? projects.map((p) => new Option(p, p))
          : [new Option("No projects yet", "")]),
      );
      get("pm-project").disabled = !projects.length;
      if (projects.includes(selection)) get("pm-project").value = selection;
      render();
      get("pm-content").hidden = false;
      get("pm-status").textContent =
        `Updated ${new Date().toLocaleTimeString()} · Saved project records`;
    } catch (error) {
      snapshot = null;
      get("pm-status").textContent =
        error.name === "TimeoutError"
          ? "Project request timed out. Refresh to retry."
          : error.message;
    } finally {
      loading = false;
      get("pm-refresh").disabled = false;
    }
  }
  get("pm-refresh").addEventListener("click", refresh);
  get("pm-project").addEventListener("change", () => {
    get("pm-search").value = "";
    render();
  });
  get("pm-search").addEventListener("input", render);
  window.addEventListener("workspace-page-changed", (event) => {
    if (event.detail.path === "/project-dashboard") refresh();
  });
  if (location.pathname === "/project-dashboard") refresh();
})();
