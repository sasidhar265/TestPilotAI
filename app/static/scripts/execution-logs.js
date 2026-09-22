/* Recorded execution evidence from the retained workspace and BDD histories. */
(() => {
  const $log = (id) => document.getElementById(id);
  const view = $log("execution-logs-view");
  if (!view) return;
  let records = [];
  let selectedId = null;
  let loading = false;
  let pageNumber = 1;
  let casePageNumber = 1;
  const pageSize = 10;
  const safe = (value) => esc(String(value ?? ""));
  const when = (value) => {
    const date = new Date(value || "");
    return Number.isNaN(date.valueOf()) ? "Not recorded" : date.toLocaleString();
  };
  const duration = (value) => `${((Number(value) || 0) / 1000).toFixed(1)} s`;
  const recorded = (value) => value || "Not recorded";
  const kind = (item) => item.operation === "case_execution" ? "Case execution" : "Repository BDD";
  const cases = (item) => item.operation === "case_execution"
    ? item.details?.cases || []
    : item.details?.test_results || [];
  const resultCounts = (item) => {
    const entries = cases(item);
    if (item.operation === "repository_checks") {
      const detail = item.details || {};
      return {
        passed: detail.passed ?? null, failed: detail.failed ?? null,
        skipped: detail.skipped ?? detail.not_run ?? null, blocked: null,
      };
    }
    return {
      passed: entries.filter((entry) => entry.execution === "passed").length,
      failed: entries.filter((entry) => entry.execution === "failed").length,
      skipped: entries.filter((entry) => ["not_run", "not-run"].includes(entry.execution)).length,
      blocked: entries.filter((entry) => entry.execution === "blocked").length,
    };
  };
  const outcome = (item) => {
    if (item.operation !== "case_execution") return item.status || "unknown";
    const values = cases(item).map((entry) => entry.execution);
    if (values.includes("failed")) return "failed";
    if (values.includes("blocked")) return "blocked";
    if (values.length && values.every((value) => value === "passed")) return "passed";
    return item.status || "completed";
  };
  const totals = (item) => {
    if (item.operation === "repository_checks") {
      const detail = item.details || {};
      if (detail.passed == null || detail.failed == null) return "Counts unavailable";
      return `${detail.passed} passed · ${detail.failed} failed · ${detail.not_run ?? detail.skipped ?? 0} not run`;
    }
    const values = cases(item);
    return `${values.filter((entry) => entry.execution === "passed").length} passed · ${values.filter((entry) => entry.execution === "failed").length} failed · ${values.length} recorded`;
  };
  const searchable = (item) => [item.id, item.status, outcome(item), kind(item), item.details?.project,
    item.details?.feature, ...cases(item).map((entry) => entry.id || entry.name)].join(" ").toLowerCase();
  function filtered() {
    const query = $log("execution-logs-search").value.trim().toLowerCase();
    const type = $log("execution-logs-type").value;
    const status = $log("execution-logs-status").value;
    const days = Number($log("execution-logs-period").value);
    const cutoff = days ? Date.now() - days * 86400000 : 0;
    return records.filter((item) =>
      (type === "all" || item.operation === type) &&
      (status === "all" || outcome(item) === status) &&
      (!cutoff || new Date(item.started_at).valueOf() >= cutoff) &&
      searchable(item).includes(query));
  }
  const detailTabs = [
    ["execution", "Execution Details"], ["report", "Report"], ["overview", "Overview"],
    ["failures", "Recent Failures"], ["cases", "Test Cases"],
    ["activity", "Agent Activity"], ["transactions", "API Transactions"],
    ["errors", "Errors & failures"], ["logs", "Technical Logs"],
  ];
  const section = (key, title, body) =>
    `<section class="execution-detail-section" id="execution-detail-panel-${key}" role="tabpanel" aria-labelledby="execution-detail-tab-${key}"${key === "execution" ? "" : " hidden"}><h4>${title}</h4>${body}</section>`;
  const facts = (items) =>
    `<dl class="execution-log-facts">${items.map(([label, value]) =>
      `<div><dt>${safe(label)}</dt><dd>${safe(value == null || value === "" ? "Not recorded" : value)}</dd></div>`).join("")}</dl>`;
  const empty = (message) => `<p class="execution-detail-empty">${safe(message)}</p>`;
  function reportMarkup(counts, scenarioCount, executedCount) {
    const outcomes = [
      ["passed", "Passed", "✓", counts.passed],
      ["failed", "Failed", "×", counts.failed],
      ["skipped", "Skipped", "↷", counts.skipped],
      ["blocked", "Blocked", "!", counts.blocked],
    ];
    const validCount = (value) => Number.isFinite(Number(value)) && Number(value) >= 0;
    const known = outcomes.filter(([, , , value]) => value != null && validCount(value));
    const total = known.reduce((sum, [, , , value]) => sum + Number(value), 0);
    let offset = 0;
    const slices = known.map(([name, , , value]) => {
      const start = offset;
      offset += total ? Number(value) / total * 100 : 0;
      return `var(--report-${name}) ${start}% ${offset}%`;
    });
    const chart = total
      ? `<div class="execution-report-donut" role="img" aria-label="${safe(known.map(([, label, , value]) => `${value} ${label.toLowerCase()}`).join(", "))}" style="background: conic-gradient(${slices.join(", ")})"><span><strong>${total}</strong><small>recorded</small></span></div>`
      : `<div class="execution-report-donut empty" role="img" aria-label="No outcome counts recorded"><span><strong>—</strong><small>recorded</small></span></div>`;
    return `<div class="execution-report-highlights">
      <article><span class="report-highlight-icon" aria-hidden="true">◇</span><div><span>Scenarios Executed</span><strong>${scenarioCount == null ? "—" : safe(scenarioCount)}</strong><small>${scenarioCount == null ? "Not recorded for this execution" : "Completed scenario outcomes"}</small></div></article>
      <article><span class="report-highlight-icon" aria-hidden="true">▣</span><div><span>Test cases Executed</span><strong>${executedCount == null ? "—" : safe(executedCount)}</strong><small>${executedCount == null ? "Not recorded for this execution" : "Cases with an execution outcome"}</small></div></article>
    </div><div class="execution-report-chart"><div><span class="section-kicker">RESULT BREAKDOWN</span><h5>Execution outcomes</h5><p>Counts from this run's recorded evidence.</p>${chart}</div><div class="execution-report-outcomes">${outcomes.map(([name, label, icon, value]) =>
      `<article class="${name}"><span class="report-outcome-icon" aria-hidden="true">${icon}</span><div><span>${label}</span><strong>${value == null || !validCount(value) ? "—" : safe(value)}</strong><small>${value == null || !validCount(value) ? "Not recorded" : "Recorded"}</small></div></article>`).join("")}</div></div>`;
  }
  function overviewMarkup(item, timeline, correlationId) {
    const result = outcome(item);
    const icon = result === "passed" ? "✓" : result === "failed" || result === "error" ? "×" : "•";
    return `<div class="execution-overview-summary ${safe(result)}"><span class="overview-result-icon" aria-hidden="true">${icon}</span><div><span class="section-kicker">EXECUTION SUMMARY</span><strong>${safe(kind(item))} · ${safe(result)}</strong><p>${safe(totals(item))}</p></div></div>
      <div class="execution-overview-grid"><div class="execution-overview-timeline"><h5>Execution timeline</h5><ol>${timeline.map(([label, time, description]) =>
        `<li><span class="timeline-node" aria-hidden="true"></span><div><time>${safe(when(time))}</time><strong>${safe(label)}</strong><p>${safe(description || "Activity recorded")}</p></div></li>`).join("")}</ol></div>
      <div class="execution-overview-reference"><h5>Run references</h5>${facts([["Correlation ID", correlationId], ["Run ID", item.id], ["Duration", item.duration_ms == null ? null : duration(item.duration_ms)]])}</div></div>`;
  }
  function executionDetailsMarkup(item, detail, suite, agent) {
    const status = outcome(item);
    const value = (entry) => safe(entry == null || entry === "" ? "Not recorded" : entry);
    return `<div class="execution-details-hero"><div><span class="section-kicker">EXECUTION RECORD</span><h5>${safe(suite)}</h5><p>${safe(kind(item))} managed by ${safe(agent)}</p></div><span class="execution-details-status ${safe(status)}"><span aria-hidden="true">●</span>${safe(status)}</span></div>
      <div class="execution-details-group"><div class="execution-details-group-heading"><span aria-hidden="true">◇</span><div><h5>Run context</h5><p>Recorded identity and ownership for this execution.</p></div></div><dl class="execution-details-grid">
        <div><dt>Execution type</dt><dd>${safe(kind(item))}</dd></div>
        <div><dt>Test suite</dt><dd>${safe(suite)}</dd></div>
        <div><dt>Agent</dt><dd>${safe(agent)}</dd></div>
        <div><dt>Environment</dt><dd>${value(detail.environment)}</dd></div>
        <div><dt>Triggered By</dt><dd>${value(detail.triggered_by)}</dd></div>
        <div><dt>Run ID</dt><dd class="execution-details-id">${safe(item.id)}</dd></div>
      </dl></div>
      <div class="execution-details-group"><div class="execution-details-group-heading"><span aria-hidden="true">◷</span><div><h5>Timing</h5><p>All timestamps are shown in your local timezone.</p></div></div><dl class="execution-details-grid timing">
        <div><dt>Start time and date</dt><dd>${safe(when(item.started_at))}</dd></div>
        <div><dt>End time and date</dt><dd>${safe(when(item.finished_at))}</dd></div>
        <div><dt>Duration</dt><dd>${item.duration_ms == null ? "Not recorded" : safe(duration(item.duration_ms))}</dd></div>
      </dl></div>`;
  }
  function agentActivityMarkup(events, fallbackAgent) {
    if (!events.length) return `<div class="execution-agent-empty"><span aria-hidden="true">◇</span><div><strong>No agent activity retained</strong><p>Agent events were not recorded for this execution.</p></div></div>`;
    return `<div class="execution-agent-heading"><span class="execution-agent-icon" aria-hidden="true">◇</span><div><span class="section-kicker">RECORDED ACTIVITY</span><strong>${events.length} ${events.length === 1 ? "event" : "events"} in this run</strong><p>Agent actions are shown in recorded order.</p></div></div>
      <div class="execution-overview-timeline execution-agent-timeline"><ol>${events.map((event) => {
        const status = String(event.status || "recorded").toLowerCase();
        return `<li><span class="timeline-node ${safe(status)}" aria-hidden="true"></span><div class="execution-agent-event"><div class="execution-agent-event-head"><time>${safe(when(event.timestamp))}</time><span class="execution-agent-status ${safe(status)}">${safe(status)}</span></div><strong>${safe(event.agent || fallbackAgent)}</strong><span class="execution-agent-action">${safe(event.action || "Activity")}</span><p>${safe(event.summary || "No summary was recorded.")}</p></div></li>`;
      }).join("")}</ol></div>`;
  }
  const caseStatus = (entry) => String(entry.execution || entry.status || "unknown").toLowerCase().replaceAll("-", "_");
  function renderCasePage() {
    const item = records.find((entry) => entry.id === selectedId);
    if (!item || !$log("execution-case-rows")) return;
    const query = $log("execution-case-search").value.trim().toLowerCase();
    const matching = cases(item).filter((entry) =>
      `${entry.title || ""} ${entry.name || ""} ${entry.id || ""} ${entry.execution || entry.status || ""}`.toLowerCase().includes(query));
    const pageCount = Math.max(1, Math.ceil(matching.length / pageSize));
    casePageNumber = Math.min(casePageNumber, pageCount);
    const page = matching.slice((casePageNumber - 1) * pageSize, casePageNumber * pageSize);
    $log("execution-case-rows").innerHTML = page.length ? page.map((entry) =>
      `<tr><th scope="row" data-label="Test case"><strong>${safe(entry.title || entry.name || entry.id || "Unnamed test")}</strong>${entry.id && (entry.title || entry.name) ? `<small>${safe(entry.id)}</small>` : ""}</th><td data-label="Outcome"><span class="execution-case-status ${safe(caseStatus(entry))}">${safe(String(entry.execution || entry.status || "Unknown").replaceAll(/[-_]/g, " "))}</span></td><td data-label="Duration">${safe(entry.duration || (entry.duration_ms != null ? duration(entry.duration_ms) : "Not recorded"))}</td><td data-label="Details" class="execution-case-details">${["failed", "error"].includes(caseStatus(entry)) ? ExecutionFailures.disclosure(entry) : safe(entry.actual_result || "—")}</td></tr>`).join("")
      : `<tr><td colspan="4" class="execution-logs-empty">${matching.length ? "No cases on this page." : "No test cases match this search."}</td></tr>`;
    $log("execution-case-page-summary").textContent = matching.length
      ? `Showing ${(casePageNumber - 1) * pageSize + 1}–${(casePageNumber - 1) * pageSize + page.length} of ${matching.length}` : "No matching cases";
    $log("execution-case-page-number").textContent = `Page ${casePageNumber} of ${pageCount}`;
    $log("execution-case-previous").disabled = casePageNumber === 1;
    $log("execution-case-next").disabled = casePageNumber === pageCount;
  }
  function technicalLogMarkup(output) {
    const lines = output ? String(output).split(/\r?\n/) : [];
    return `<div class="execution-technical-toolbar"><div><span class="section-kicker">RUNNER OUTPUT</span><strong>${lines.length} ${lines.length === 1 ? "line" : "lines"} recorded</strong></div><div><input id="execution-technical-search" type="search" placeholder="Find in logs…" aria-label="Find in technical logs" /><button type="button" class="secondary" id="execution-technical-copy" ${lines.length ? "" : "disabled"}>Copy logs</button></div></div>
      <div class="execution-technical-console" id="execution-technical-console" role="log" aria-label="Runner technical output"></div>
      <div class="execution-correlated-logs" id="execution-correlated-logs"></div>`;
  }
  function renderTechnicalLines() {
    const item = records.find((entry) => entry.id === selectedId);
    const target = $log("execution-technical-console");
    if (!item || !target) return;
    const output = item.details?.output || "";
    const query = $log("execution-technical-search").value.trim().toLowerCase();
    const lines = output ? String(output).split(/\r?\n/) : [];
    const matching = lines.map((line, index) => [line, index + 1]).filter(([line]) => line.toLowerCase().includes(query));
    target.innerHTML = matching.length ? matching.map(([line, number]) => {
      const severity = /\b(error|failed|exception|fatal)\b/i.test(line) ? "error" : /\b(warn|warning|skipped)\b/i.test(line) ? "warning" : "normal";
      return `<div class="execution-technical-line ${severity}"><span aria-hidden="true">${number}</span><code>${safe(line || " ")}</code></div>`;
    }).join("") : empty(lines.length ? "No log lines match this search." : "No runner output was retained.");
  }
  function drawDetail(item) {
    const detail = item.details || {};
    const entries = cases(item);
    const counts = resultCounts(item);
    const events = Array.isArray(item.events) ? item.events : [];
    const failures = entries.filter((entry) =>
      ["failed", "error"].includes(String(entry.execution || entry.status).toLowerCase()));
    const agent = item.operation === "repository_checks" ? "Automation Execution Agent" : "Execution Agent";
    const suite = detail.feature || detail.project || "Not recorded";
    const correlationId = item.request_id && item.request_id !== "-" ? item.request_id : null;
    const scenarioCount = item.operation === "repository_checks" &&
      counts.passed != null && counts.failed != null ? counts.passed + counts.failed : null;
    const executedCount = item.operation === "repository_checks"
      ? counts.passed == null || counts.failed == null ? null : counts.passed + counts.failed
      : entries.filter((entry) => !["not_run", "not-run"].includes(entry.execution)).length;
    const timeline = [
      ["Started", item.started_at, "Execution started"],
      ...events.map((event) => [event.status || "Activity", event.timestamp, event.summary || event.action]),
      ["Finished", item.finished_at, "Execution finished"],
    ].filter((entry) => entry[1]);
    const reportAvailable = detail.report_available && /^[a-f0-9]{32}$/.test(detail.report_id || "");
    const download = $log("execution-log-allure-download");
    download.hidden = !reportAvailable;
    if (reportAvailable) download.href = `/api/automation/reports/${detail.report_id}`;
    else download.removeAttribute("href");
    $log("execution-detail-tabs").innerHTML = detailTabs.map(([key, title], index) =>
      `<button type="button" id="execution-detail-tab-${key}" role="tab" data-detail-tab="${key}" aria-controls="execution-detail-panel-${key}" aria-selected="${index === 0}" tabindex="${index === 0 ? 0 : -1}">${title}</button>`).join("");
    $log("execution-log-detail-title").textContent = `${kind(item)} · ${when(item.started_at)}`;
    $log("execution-log-detail-content").innerHTML =
      section("execution", "Execution Details", executionDetailsMarkup(item, detail, suite, agent)) +
      section("report", "Report", reportMarkup(counts, scenarioCount, executedCount) +
        (reportAvailable ? empty("Allure report is ready. Use Download Allure report above.") : empty(detail.report_error || "No downloadable report was recorded for this run."))) +
      section("overview", "Overview", overviewMarkup(item, timeline, correlationId)) +
      section("failures", "Recent Failures", failures.length
        ? `<div class="test-failure-list">${failures.map(ExecutionFailures.card).join("")}</div>`
        : empty("No failed test cases were recorded.")) +
      section("cases", "Test Cases", entries.length
        ? `<div class="execution-case-toolbar"><span>${entries.length} recorded test cases</span><input id="execution-case-search" type="search" placeholder="Search test cases…" aria-label="Search test cases" /></div><div class="execution-logs-table-wrap execution-case-table-wrap"><table class="execution-logs-table execution-case-table"><thead><tr><th>Test case</th><th>Outcome</th><th>Duration</th><th>Details</th></tr></thead><tbody id="execution-case-rows"></tbody></table></div><nav class="execution-logs-pagination" aria-label="Test case pages"><span id="execution-case-page-summary"></span><div><button type="button" class="secondary" id="execution-case-previous">Previous</button><span id="execution-case-page-number"></span><button type="button" class="secondary" id="execution-case-next">Next</button></div></nav>`
        : empty("No test-level results were recorded for this execution.")) +
      section("activity", "Agent Activity", agentActivityMarkup(events, agent)) +
      section("transactions", "API Transactions", '<div id="execution-api-transactions">' + empty("Checking correlated API activity…") + "</div>") +
      section("errors", "Errors & failures", detail.error || failures.length
        ? `${detail.error ? `<p class="execution-log-error">${safe(detail.error)}</p>` : ""}<div class="test-failure-list">${failures.map(ExecutionFailures.card).join("")}</div>`
        : empty("No error details were recorded.")) +
      section("logs", "Technical Logs", technicalLogMarkup(detail.output));
    casePageNumber = 1;
    renderCasePage();
    renderTechnicalLines();
  }
  function activateDetailTab(key, focus = false) {
    detailTabs.forEach(([tabKey]) => {
      const tab = $log(`execution-detail-tab-${tabKey}`);
      const panel = $log(`execution-detail-panel-${tabKey}`);
      const active = tabKey === key;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      panel.hidden = !active;
      if (active && focus) tab.focus();
    });
  }
  async function loadCorrelatedLogs(item) {
    const requestId = item.request_id;
    const apiTarget = $log("execution-api-transactions");
    const logTarget = $log("execution-correlated-logs");
    if (!requestId || requestId === "-" || !/^[A-Za-z0-9._-]{1,128}$/.test(requestId)) {
      apiTarget.innerHTML = empty("No correlation ID was recorded for API transactions.");
      return;
    }
    try {
      const response = await fetch(`/api/logs?request_id=${encodeURIComponent(requestId)}&limit=200`,
        { signal: AbortSignal.timeout(10000) });
      if (!response.ok) throw new Error("Correlated logs unavailable");
      const data = await response.json();
      if (selectedId !== item.id || !Array.isArray(data.entries)) return;
      const transactions = data.entries.filter((entry) =>
        /\b(GET|POST|PUT|PATCH|DELETE)\b|HTTP Request/i.test(entry.message || ""));
      apiTarget.innerHTML = transactions.length
        ? `<ol>${transactions.map((entry) => `<li><time>${safe(when(entry.timestamp))}</time> ${safe(entry.message)}</li>`).join("")}</ol>`
        : empty("No API transactions were retained for this correlation ID.");
      logTarget.innerHTML = data.entries.length
        ? `<div class="execution-app-logs-head"><span class="section-kicker">APPLICATION LOGS</span><strong>${data.entries.length} correlated entries</strong></div><div class="execution-app-log-list">${data.entries.map((entry) =>
          `<article><time>${safe(when(entry.timestamp))}</time><span class="execution-app-log-level ${safe(String(entry.level || "info").toLowerCase())}">${safe(entry.level || "INFO")}</span><p>${safe(entry.message)}</p></article>`).join("")}</div>`
        : empty("No application logs were retained for this correlation ID.");
    } catch {
      if (selectedId !== item.id) return;
      apiTarget.innerHTML = empty("Correlated API transactions are unavailable.");
      logTarget.innerHTML = empty("Correlated application logs are unavailable.");
    }
  }
  function draw() {
    const visible = filtered();
    const pageCount = Math.max(1, Math.ceil(visible.length / pageSize));
    pageNumber = Math.min(pageNumber, pageCount);
    const page = visible.slice((pageNumber - 1) * pageSize, pageNumber * pageSize);
    const outcomes = records.map(outcome);
    $log("execution-logs-metrics").innerHTML = [
      ["Overall runs", records.length],
      ["Passed", outcomes.filter((value) => value === "passed").length],
      ["Failed", outcomes.filter((value) => value === "failed").length],
      ["Other outcomes", outcomes.filter((value) => !["passed", "failed"].includes(value)).length],
    ].map(([label, value]) => `<article><span>${label}</span><strong>${value}</strong></article>`).join("");
    const passed = outcomes.filter((value) => value === "passed").length;
    const failed = outcomes.filter((value) => value === "failed").length;
    const other = records.length - passed - failed;
    const latest = records[0];
    $log("execution-logs-overview").innerHTML =
      `<div><span class="section-kicker">OVERALL RUNS</span><h3>Outcome distribution</h3><p>All retained executions, before filters.</p><div class="execution-outcome-bar" role="img" aria-label="${passed} passed, ${failed} failed, ${other} other outcomes">${records.length ? [
        ["passed", passed], ["failed", failed], ["other", other],
      ].map(([name, count]) => `<span class="${name}" style="width:${count / records.length * 100}%"></span>`).join("") : ""}</div><div class="execution-outcome-legend"><span>${passed} passed</span><span>${failed} failed</span><span>${other} other</span></div></div>` +
      `<div><span class="section-kicker">LATEST EXECUTION</span><h3>${latest ? safe(kind(latest)) : "No runs recorded"}</h3><p>${latest ? `${safe(when(latest.started_at))} · ${safe(outcome(latest))}` : "Run a suite to start execution history."}</p><strong>${latest ? safe(totals(latest)) : "—"}</strong></div>`;
    $log("execution-logs-rows").innerHTML = page.length
      ? page.map((item) => `<tr><th scope="row" data-label="Execution"><strong>${safe(kind(item))}</strong><small>${safe(item.details?.feature || item.details?.project || item.id)}</small></th><td data-label="Started">${safe(when(item.started_at))}</td><td data-label="Status"><span class="execution-log-status ${safe(outcome(item))}">${safe(outcome(item))}</span></td><td data-label="Results">${safe(totals(item))}</td><td data-label="Duration">${safe(duration(item.duration_ms))}</td><td data-label="View"><button type="button" class="execution-log-view" data-log-id="${safe(item.id)}" aria-label="View details for ${safe(kind(item))} from ${safe(when(item.started_at))}" title="View execution details"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.8"/></svg></button></td></tr>`).join("")
      : `<tr><td colspan="6" class="execution-logs-empty">${records.length ? "No executions match these filters." : "No recorded executions yet."}</td></tr>`;
    $log("execution-logs-status-text").textContent = `${visible.length} of ${records.length} retained executions match the filters.`;
    $log("execution-logs-page-summary").textContent = visible.length
      ? `Showing ${(pageNumber - 1) * pageSize + 1}–${(pageNumber - 1) * pageSize + page.length} of ${visible.length}`
      : "No matching executions";
    $log("execution-logs-page-number").textContent = `Page ${pageNumber} of ${pageCount}`;
    $log("execution-logs-previous").disabled = pageNumber === 1;
    $log("execution-logs-next").disabled = pageNumber === pageCount;
  }
  async function refresh() {
    if (loading) return;
    loading = true;
    $log("execution-logs-status-text").textContent = "Loading execution history…";
    try {
      const [workspaceResponse, bddResponse] = await Promise.all([
        fetch("/api/dashboard", { signal: AbortSignal.timeout(15000) }),
        fetch("/api/automation/history", { signal: AbortSignal.timeout(15000) }),
      ]);
      if (!workspaceResponse.ok || !bddResponse.ok) throw new Error("Execution history could not be loaded.");
      const [workspace, bdd] = await Promise.all([workspaceResponse.json(), bddResponse.json()]);
      if (!Array.isArray(workspace.history) || !Array.isArray(bdd.history)) throw new Error("Execution history is unavailable.");
      const merged = new Map();
      workspace.history.filter((item) => item.operation === "case_execution").forEach((item) => merged.set(item.id, item));
      bdd.history.filter((item) => item.operation === "repository_checks").forEach((item) => merged.set(item.id, item));
      records = [...merged.values()].sort((a, b) => new Date(b.started_at) - new Date(a.started_at));
      $log("execution-logs-scope").textContent = "Retained history: up to 200 recent workspace actions and 200 repository BDD runs. Times are shown in your local timezone.";
      draw();
    } catch (error) {
      $log("execution-logs-status-text").textContent = `${error.message} Select Refresh logs to retry.`;
      $log("execution-logs-rows").innerHTML = '<tr><td colspan="6" class="execution-logs-empty">History unavailable.</td></tr>';
      $log("execution-logs-metrics").innerHTML = "";
      $log("execution-logs-overview").innerHTML = "";
      if ($log("execution-log-detail").open) $log("execution-log-detail").close();
    } finally {
      loading = false;
    }
  }
  document.querySelectorAll("[data-execution-view]").forEach((button) => button.addEventListener("click", () => {
    const logs = button.dataset.executionView === "logs";
    $log("progress-dashboard-view").hidden = logs;
    view.hidden = !logs;
    document.querySelectorAll("[data-execution-view]").forEach((tab) => {
      tab.classList.toggle("active", tab === button);
      if (tab === button) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
    });
    if (logs) refresh();
  }));
  ["execution-logs-search", "execution-logs-type", "execution-logs-status", "execution-logs-period"].forEach((id) =>
    $log(id).addEventListener(id === "execution-logs-search" ? "input" : "change", () => {
      pageNumber = 1;
      draw();
    }));
  $log("execution-logs-previous").addEventListener("click", () => {
    pageNumber = Math.max(1, pageNumber - 1);
    draw();
  });
  $log("execution-logs-next").addEventListener("click", () => {
    pageNumber += 1;
    draw();
  });
  $log("execution-logs-refresh").addEventListener("click", refresh);
  $log("execution-detail-tabs").addEventListener("click", (event) => {
    const tab = event.target.closest("[data-detail-tab]");
    if (tab) activateDetailTab(tab.dataset.detailTab);
  });
  $log("execution-detail-tabs").addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const current = detailTabs.findIndex(([key]) => key === document.activeElement?.dataset.detailTab);
    if (current < 0) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? detailTabs.length - 1
      : (current + (event.key === "ArrowRight" ? 1 : -1) + detailTabs.length) % detailTabs.length;
    activateDetailTab(detailTabs[next][0], true);
  });
  $log("execution-log-detail-content").addEventListener("input", (event) => {
    if (event.target.id === "execution-case-search") {
      casePageNumber = 1;
      renderCasePage();
    }
    if (event.target.id === "execution-technical-search") renderTechnicalLines();
  });
  $log("execution-log-detail-content").addEventListener("click", async (event) => {
    if (event.target.id === "execution-case-previous") {
      casePageNumber = Math.max(1, casePageNumber - 1);
      renderCasePage();
    }
    if (event.target.id === "execution-case-next") {
      casePageNumber += 1;
      renderCasePage();
    }
    if (event.target.id === "execution-technical-copy") {
      const output = records.find((item) => item.id === selectedId)?.details?.output;
      if (!output) return;
      try {
        await navigator.clipboard.writeText(String(output));
        event.target.textContent = "Copied";
      } catch {
        event.target.textContent = "Copy unavailable";
      }
    }
  });
  $log("execution-logs-rows").addEventListener("click", (event) => {
    const button = event.target.closest("[data-log-id]");
    if (!button) return;
    selectedId = button.dataset.logId;
    const item = records.find((entry) => entry.id === selectedId);
    if (!item) return;
    drawDetail(item);
    $log("execution-log-detail").showModal();
    loadCorrelatedLogs(item);
  });
  $log("execution-log-detail-close").addEventListener("click", () => {
    $log("execution-log-detail").close();
  });
  $log("execution-log-detail").addEventListener("close", () => { selectedId = null; });
  $log("execution-log-detail").addEventListener("click", (event) => {
    if (event.target === $log("execution-log-detail")) $log("execution-log-detail").close();
  });
})();
