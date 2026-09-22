/* Management reporting uses recorded suite versions, never inferred project outcomes. */
(() => {
  const get = (id) => document.getElementById(id);
  let snapshot = null;
  let loading = false;
  const date = (value) => (value ? new Date(value).toLocaleString() : "Unavailable");
  function render() {
    if (!snapshot) return;
    const days = Number(get("pm-period").value);
    const cutoff = days ? Date.now() - days * 86400000 : -Infinity;
    const query = get("pm-search").value.trim().toLowerCase();
    const history = snapshot.history.filter(
      (item) =>
        Date.parse(item.finished_at || item.started_at) >= cutoff &&
        (!query || (item.details?.feature || "").toLowerCase().includes(query)),
    );
    const versions = new Map();
    const ordered = [...history].sort(
      (a, b) =>
        Date.parse(b.finished_at || b.started_at) - Date.parse(a.finished_at || a.started_at),
    );
    for (const item of ordered) {
      if (
        !["test_generation", "case_execution"].includes(item.operation) ||
        !item.details?.suite_key
      )
        continue;
      const key = item.details.suite_key;
      if (!versions.has(key))
        versions.set(key, {
          key,
          feature: item.details.feature || "Unnamed feature",
          updated: item.finished_at || item.started_at,
        });
      const entry = versions.get(key);
      if (!entry[item.operation]) entry[item.operation] = item.details;
    }
    const suites = [...versions.values()];
    const counts = { passed: 0, failed: 0, blocked: 0, not_run: 0, unknown: 0 };
    let cases = 0,
      valid = 0,
      missingExecution = 0;
    for (const entry of suites) {
      const records = entry.test_generation?.cases || entry.case_execution?.cases || [];
      cases += records.length;
      if (entry.test_generation?.validated === true) valid++;
      if (!entry.case_execution) missingExecution++;
      for (const item of entry.case_execution?.cases || []) {
        const normalized = item.execution === "not-run" ? "not_run" : item.execution;
        const status = Object.hasOwn(counts, normalized) ? normalized : "unknown";
        counts[status]++;
      }
    }
    const generationProblems = history.filter(
      (item) =>
        item.operation === "test_generation" &&
        ["failed", "error", "cancelled", "validation_failed"].includes(item.status),
    ).length;
    const active = snapshot.active.length;
    const metric = (label, value, hint) =>
      `<article class="pm-card"><span>${esc(label)}</span><strong>${value}</strong><small>${esc(hint)}</small></article>`;
    get("pm-metrics").innerHTML =
      metric("Suite versions", suites.length, `${cases} cases across retained versions`) +
      metric(
        "Design validation passed",
        valid,
        `Of ${suites.length} suite versions; not execution approval`,
      ) +
      metric(
        "Failed / blocked cases",
        counts.failed + counts.blocked,
        "Latest recorded case results per version",
      ) +
      metric(
        "Active workspace actions",
        active,
        "All features; current server activity, independent of filters",
      );
    const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
    get("pm-outcomes").innerHTML = total
      ? Object.entries(counts)
          .map(
            ([status, count]) =>
              `<div class="pm-outcome" data-outcome="${status}"><span>${esc(status.replaceAll("_", " "))}</span><meter min="0" max="${total}" value="${count}" aria-label="${status}"></meter><strong>${count}</strong></div>`,
          )
          .join("")
      : '<p class="pm-empty">No case execution evidence in this selection.</p>';
    const attention = [];
    if (missingExecution)
      attention.push(
        `${missingExecution} suite versions have no recorded case execution in this selection.`,
      );
    if (counts.failed || counts.blocked)
      attention.push(
        `${counts.failed} failed and ${counts.blocked} blocked cases need investigation.`,
      );
    if (counts.not_run || counts.unknown)
      attention.push(
        `${counts.not_run} cases not run and ${counts.unknown} cases with unknown outcomes need follow-up.`,
      );
    if (suites.length - valid)
      attention.push(
        `${suites.length - valid} suite versions lack a recorded passing design validation in this selection.`,
      );
    if (generationProblems)
      attention.push(
        `${generationProblems} generation attempts failed, were cancelled, or did not pass validation.`,
      );
    if (!attention.length)
      attention.push(
        suites.length
          ? "No issues identified by these recorded indicators. Confirm approval and release decisions with your team."
          : "No suite activity matches this selection. Broaden the period or generate a suite.",
      );
    get("pm-attention").innerHTML = attention.map((item) => `<li>${esc(item)}</li>`).join("");
    get("pm-suite-count").textContent = `${suites.length} versions`;
    get("pm-suites").innerHTML = suites.length
      ? suites
          .map((entry) => {
            const outcomes = entry.case_execution?.cases || [];
            const summary = entry.case_execution
              ? `${outcomes.filter((c) => c.execution === "passed").length} passed / ${outcomes.length} recorded`
              : "No evidence";
            const validation =
              entry.test_generation?.validated === true
                ? "Passed"
                : entry.test_generation?.validated === false
                  ? "Not passed"
                  : "Unavailable";
            return `<tr><th scope="row">${esc(entry.feature)}<small>${esc(entry.key.slice(0, 12))}</small></th><td>${(entry.test_generation?.cases || outcomes).length}</td><td>${validation}</td><td>${summary}</td><td>${esc(date(entry.updated))}</td></tr>`;
          })
          .join("")
      : '<tr><td colspan="5" class="pm-empty">No suite versions match the current filters.</td></tr>';
    get("pm-scope").textContent =
      snapshot.scope || "Retained workspace history; not a complete project inventory.";
  }
  async function refresh() {
    if (loading) return;
    loading = true;
    get("pm-refresh").disabled = true;
    get("pm-content").hidden = true;
    get("pm-status").textContent = "Loading workspace evidence…";
    try {
      const response = await fetch("/api/dashboard", { signal: AbortSignal.timeout(15000) });
      if (!response.ok)
        throw new Error("Dashboard data could not be loaded. Use Refresh dashboard to retry.");
      const data = await response.json();
      if (!Array.isArray(data.history) || !Array.isArray(data.active))
        throw new Error("Dashboard history is unavailable. Use Refresh dashboard to retry.");
      snapshot = data;
      render();
      get("pm-content").hidden = false;
      get("pm-status").textContent =
        `Updated ${new Date().toLocaleTimeString()} · Retained workspace history`;
    } catch (error) {
      snapshot = null;
      get("pm-status").textContent =
        error.name === "TimeoutError"
          ? "Dashboard request timed out. Refresh to retry."
          : error.message;
    } finally {
      loading = false;
      get("pm-refresh").disabled = false;
    }
  }
  get("pm-refresh").addEventListener("click", refresh);
  get("pm-period").addEventListener("change", render);
  get("pm-search").addEventListener("input", render);
  window.addEventListener("workspace-page-changed", (event) => {
    if (event.detail.path === "/project-dashboard") refresh();
  });
  if (location.pathname === "/project-dashboard") refresh();
})();
