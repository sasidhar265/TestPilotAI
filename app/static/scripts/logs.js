const $ = (id) => document.getElementById(id);
const activityView = new URLSearchParams(location.search).get("view") === "activity";
let activityController = null;
let activityReference = "";
const esc = (value) =>
  String(value).replace(
    /[&<>'"]/g,
    (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char],
  );
function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  if ($("log-timezone").value === "utc")
    return date.toISOString().replace("T", " ").replace("Z", " UTC");
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
    timeZoneName: "short",
  }).format(date);
}
function setState(title, message) {
  $("log-state").innerHTML =
    `<span class="empty-icon">⌕</span><h3>${esc(title)}</h3><p>${esc(message)}</p>`;
  $("log-state").classList.remove("hidden");
}
let logEntries = [];
let logLevel = "all";
let logsLoaded = false;
let loading = false;
let pendingLoad = null;
let referenceFilter = "";
let shownEntries = [];
let logPage = 1;
const openRecords = new Set();
function logRecords(entries) {
  const records = new Map();
  const rank = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4 };
  entries.forEach((entry, index) => {
    const key =
      entry.request_id && entry.request_id !== "-"
        ? entry.request_id
        : `${entry.timestamp}:${entry.logger}:${entry.message}:${index}`;
    if (!records.has(key)) records.set(key, { key, entries: [], level: "DEBUG" });
    const record = records.get(key);
    record.entries.push(entry);
    if ((rank[entry.level] ?? 1) > (rank[record.level] ?? 0)) record.level = entry.level;
  });
  return [...records.values()]
    .map((record) => {
      record.entries.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
      const last = record.entries.at(-1);
      const completion = [...record.entries]
        .reverse()
        .find((e) => e.message.startsWith("request_complete"));
      const main = completion || last;
      const fields = main.details || {};
      const names = {
        "/api/stlc": "Knowledge graph data",
        "/api/logs": "Runtime logs",
        "/api/auth/login": "Sign-in",
        "/api/generate": "Test generation",
        "/api/workflow/stories": "User story generation",
        "/api/workflow/scenarios": "Scenario generation",
        "/api/workflow/test-cases": "Test case generation",
        "/api/agent/run": "Agent execution",
      };
      record.title =
        names[fields.path] ||
        (fields.path
          ? `${fields.method || "API"} ${fields.path}`
          : fields.operation
            ? String(fields.operation).replaceAll("_", " ")
            : fields.agent
              ? `${fields.agent} activity`
              : "Application activity");
      record.outcome = ["ERROR", "CRITICAL"].includes(record.level)
        ? "Needs attention"
        : Number(fields.status) >= 400
          ? "Request rejected"
          : completion
            ? "Completed"
            : fields.status || fields.outcome || "Activity recorded";
      record.timestamp = last.timestamp;
      record.duration = fields.duration_ms;
      record.reference = main.request_id;
      return record;
    })
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
}
function eventMarkup(entry) {
  return `<li class="record-event">
    <div class="record-event-heading"><span class="severity">${esc(entry.level)}</span>
    <time datetime="${esc(entry.timestamp)}">${esc(formatTime(entry.timestamp))}</time><span>${esc(entry.logger)}</span></div>
    <p class="message">${esc(entry.message)}</p>
    ${
      entry.details && Object.keys(entry.details).length
        ? `<section class="event-detail"><h4>Event details</h4><dl>${Object.entries(entry.details)
            .map(
              ([key, value]) =>
                `<div><dt>${esc(key.replaceAll("_", " "))}</dt><dd>${esc(value)}</dd></div>`,
            )
            .join("")}</dl></section>`
        : ""
    }
    ${entry.exception ? `<section class="exception"><h4>Technical details</h4><pre>${esc(entry.exception)}</pre></section>` : ""}
    <details class="log-raw"><summary>Structured log entry</summary><pre>${esc(JSON.stringify(entry, null, 2))}</pre></details>
  </li>`;
}
function renderLogs(preserveScroll = false, expandAll) {
  document.querySelectorAll(".log-row").forEach((row) => {
    if (row.open) openRecords.add(row.dataset.logKey);
    else openRecords.delete(row.dataset.logKey);
  });
  if (expandAll !== undefined) openRecords.clear();
  const query = $("log-reference").value.toLowerCase().trim();
  const records = logRecords(logEntries).filter(
    (record) =>
      (logLevel === "all" || record.level.toUpperCase() === logLevel) &&
      (!query ||
        `${record.title} ${record.outcome} ${JSON.stringify(record.entries)}`
          .toLowerCase()
          .includes(query)),
  );
  shownEntries = records.flatMap((record) => record.entries);
  const pageSize = Number($("log-page-size").value);
  const pages = Math.max(1, Math.ceil(records.length / pageSize));
  logPage = Math.min(logPage, pages);
  const start = (logPage - 1) * pageSize;
  $("log-page-status").textContent = `Page ${logPage} of ${pages}`;
  $("log-page-range").textContent = records.length
    ? `${start + 1}–${Math.min(start + pageSize, records.length)} of ${records.length} loaded records`
    : "0 loaded records";
  $("log-page-previous").disabled = logPage === 1;
  $("log-page-next").disabled = logPage === pages;
  const scroll = document.querySelector(".logs-scroll").scrollTop;
  $("log-count").textContent = `${records.length} records`;
  if (!records.length) {
    $("log-results").replaceChildren();
    setState(
      "No matching records",
      logEntries.length
        ? "Clear the search or choose another status."
        : "No recent activity for this reference. The in-process viewer clears on restart.",
    );
    return;
  }
  $("log-state").classList.add("hidden");
  $("log-results").innerHTML = records.slice(start, start + pageSize)
    .map((record) => {
      const expanded =
        expandAll !== undefined
          ? expandAll
          : $("log-detailed").checked || openRecords.has(record.key);
      return `<details class="log-row severity-${esc(record.level.toLowerCase())}" data-log-key="${esc(record.key)}" ${expanded ? "open" : ""}>
      <summary class="log-record-summary">
        <span class="severity"><span class="severity-dot"></span>${esc(record.level)}</span>
        <span class="record-overview"><strong>${esc(record.title)}</strong><span class="metadata"><time datetime="${esc(record.timestamp)}">${esc(formatTime(record.timestamp))}</time><span>${record.entries.length} events${record.duration !== undefined ? ` · ${esc(record.duration)} ms` : ""}</span></span></span>
        <span class="record-outcome">${esc(record.outcome)}</span><span class="record-chevron" aria-hidden="true">⌄</span>
      </summary>
      <div class="log-record-detail">
        <div class="record-detail-head"><h3>Activity timeline</h3>${record.reference && record.reference !== "-" ? `<button class="reference" type="button" data-reference="${esc(record.reference)}" title="Search this reference ID"><span>REFERENCE ID</span><code>${esc(record.reference)}</code></button>` : ""}</div>
        <p class="record-scope">${record.entries.length} events from the loaded log window. Older events may be in the rotating server files.</p>
        <ol class="record-timeline">${record.entries.map(eventMarkup).join("")}</ol>
      </div>
    </details>`;
    })
    .join("");
  document.querySelector(".logs-scroll").scrollTop = preserveScroll ? scroll : 0;
}
async function loadLogs(reference = "", background = false) {
  if (loading) {
    if (!background) pendingLoad = { reference };
    return;
  }
  loading = true;
  if (reference !== referenceFilter) logPage = 1;
  referenceFilter = reference;
  if (activityView) loadRequestActivity(reference);
  const query = new URLSearchParams({ limit: $("log-limit").value });
  if (reference) query.set("request_id", reference);
  if (!background) {
    logsLoaded = false;
    $("log-count").textContent = "…";
  }
  $("result-title").textContent = reference ? activityView ? "Technical request logs" : "Search results" : "Recent logs";
  if (!background) setState("Searching logs", "Reading local application activity…");
  try {
    const response = await fetch(`/api/logs?${query}`);
    if (!response.ok) throw new Error(`Log request failed (${response.status})`);
    const data = await response.json();
    $("log-count").textContent = String(data.count);
    logEntries = data.entries;
    logsLoaded = true;
    renderLogs(background);
    $("log-updated").textContent =
      `Updated ${formatTime(new Date().toISOString())} · ${logEntries.length} entries loaded`;
  } catch (error) {
    $("log-count").textContent = "!";
    $("log-updated").textContent = error.message;
    if (!background) setState("Logs unavailable", error.message);
  } finally {
    loading = false;
    if (pendingLoad) {
      const next = pendingLoad;
      pendingLoad = null;
      loadLogs(next.reference);
    }
  }
}
async function loadRequestActivity(reference) {
  activityController?.abort();
  const panel = $("request-activity");
  panel.hidden = !reference;
  if (reference !== activityReference) {
    $("request-activity-events").replaceChildren();
    $("request-activity-status").textContent = "Loading agent activity…";
    activityReference = reference;
  }
  if (!reference) return;
  const controller = new AbortController();
  activityController = controller;
  $("request-activity-reference").textContent = `Reference ID: ${reference}`;
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(`/api/generation/${encodeURIComponent(reference)}/events`, {
      signal: controller.signal, cache: "no-store",
    });
    if (!response.ok) throw new Error(`Activity request failed (${response.status})`);
    const data = await response.json();
    if (activityController !== controller) return;
    const events = [], waiting = new Map();
    for (const event of data.events || []) {
      if (event.action === "provider_wait") {
        const key = event.summary.replace(/\(\d+s elapsed\)/g, "(elapsed)");
        const prior = waiting.get(event.agent);
        if (prior?.key === key) events[prior.index] = event;
        else {
          waiting.set(event.agent, { key, index: events.length });
          events.push(event);
        }
      } else {
        if (event.action?.startsWith("provider_")) waiting.delete(event.agent);
        events.push(event);
      }
    }
    $("request-activity-events").innerHTML = events.map((event) => {
      const label = event.action === "provider_wait" ? "Waiting update"
        : ["running", "started"].includes(event.status) ? "Started" : event.status;
      return `<li class="record-event"><div class="record-event-heading"><strong>${esc(event.agent)}</strong><span>${esc(label)} · ${esc((event.action || "activity").replaceAll("_", " "))}</span><time>${esc(formatTime(event.timestamp))}</time></div><p class="activity-summary">${esc(event.summary)}</p></li>`;
    }).join("");
    $("request-activity-status").textContent = events.length
      ? `${data.complete ? "Backend activity finished" : "Live activity"} · ${events.length} displayed checkpoints. Updated ${formatTime(new Date().toISOString())}.`
      : "No backend checkpoints are available for this reference yet. Older activity may have expired or been cleared by a server restart.";
  } catch (error) {
    if (activityController !== controller) return;
    $("request-activity-status").textContent = "Agent activity could not be loaded. Any displayed timeline is from an earlier refresh. Live updates will retry; technical request logs are shown separately below.";
  } finally {
    clearTimeout(timeout);
  }
}
function searchLogs() {
  const value = $("log-reference").value.trim();
  const matchesText = logEntries.some((entry) =>
    JSON.stringify(entry).toLowerCase().includes(value.toLowerCase()),
  );
  const exactReference = logEntries.some((entry) => entry.request_id === value);
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  loadLogs(value && (exactReference || uuid || !matchesText) ? value : "");
}
$("search-logs").onclick = searchLogs;
$("log-reference").addEventListener("keydown", (event) => {
  if (event.key === "Enter") searchLogs();
});
$("log-reference").addEventListener("input", () => {
  logPage = 1;
  if (referenceFilter && $("log-reference").value.trim() !== referenceFilter) loadLogs("");
  renderLogs();
});
$("log-results").addEventListener("click", (event) => {
  const button = event.target.closest(".reference");
  if (!button) return;
  $("log-reference").value = button.dataset.reference;
  loadLogs(button.dataset.reference);
});
fetch("/api/health")
  .then((response) => {
    if (!response.ok) throw new Error();
    $("service-state").textContent = "● Service online";
    $("service-state").classList.add("live");
  })
  .catch(() => {
    $("service-state").textContent = "● Service unavailable";
  });
const initialReference = new URLSearchParams(window.location.search).get("request_id") || "";
if (activityView) {
  document.querySelector(".topbar h1").textContent = "Operation activity";
  document.querySelector(".explore-banner").hidden = true;
  document.title = "Operation activity · Auto Finance Quality";
}
$("log-reference").value = initialReference;
loadLogs(initialReference);

$("log-status-menu").addEventListener("click", (event) => {
  const button = event.target.closest("[data-log-level]");
  if (!button) return;
  logLevel = button.dataset.logLevel;
  logPage = 1;
  $("log-status-label").textContent = button.textContent;
  document
    .querySelectorAll("[data-log-level]")
    .forEach((option) => option.setAttribute("aria-pressed", String(option === button)));
  $("log-status-menu").open = false;
  $("log-status-menu").querySelector("summary").focus();
  if (logsLoaded) renderLogs();
});
document.addEventListener("click", (event) => {
  if (!$("log-status-menu").contains(event.target)) $("log-status-menu").open = false;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && $("log-status-menu").open) {
    $("log-status-menu").open = false;
    $("log-status-menu").querySelector("summary").focus();
  }
});

$("log-refresh").addEventListener("click", () => loadLogs(referenceFilter));
$("log-limit").addEventListener("change", () => loadLogs(referenceFilter));
$("log-page-size").addEventListener("change", () => {
  logPage = 1;
  renderLogs();
});
$("log-page-previous").addEventListener("click", () => {
  if (logPage > 1) { logPage -= 1; renderLogs(); }
});
$("log-page-next").addEventListener("click", () => {
  if (!$("log-page-next").disabled) { logPage += 1; renderLogs(); }
});
$("log-timezone").addEventListener("change", () => renderLogs());
$("log-download").addEventListener("click", () => {
  const url = URL.createObjectURL(
    new Blob([shownEntries.map((entry) => JSON.stringify(entry)).join("\n") + "\n"], {
      type: "application/x-ndjson",
    }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `runtime-logs-${new Date().toISOString().replaceAll(":", "-")}.jsonl`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
setInterval(() => {
  if (
    $("log-live").checked &&
    !document.hidden &&
    !document.querySelector("#log-results .log-raw:focus-within")
  )
    loadLogs(referenceFilter, true);
}, 5000);

$("log-detailed").addEventListener("change", () => renderLogs(false, $("log-detailed").checked));

const viewMenu = $("log-view-menu");
viewMenu.addEventListener("toggle", () => {
  if (viewMenu.open) $("log-status-menu").open = false;
});
$("log-status-menu").addEventListener("toggle", () => {
  if ($("log-status-menu").open) viewMenu.open = false;
});
document.addEventListener("click", (event) => {
  if (!viewMenu.contains(event.target)) viewMenu.open = false;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && viewMenu.open) {
    viewMenu.open = false;
    viewMenu.querySelector("summary").focus();
  }
});
