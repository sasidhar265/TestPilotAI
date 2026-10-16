/* Page behavior only. The matching HTML defines structure and CSS defines appearance. */

let reviewSourceRequest = null;
const generationOperation = window.createOperationProgress();
let suite = null,
  validationReport = null,
  stepDefinitionArtifact = null,
  attachedFile = null,
  activeGeneration = null,
  generationSubmitPending = false,
  executionSummary = null,
  defectDrafts = [],
  activeLifecycleTimer = null,
  activeLifecycleRequestId = null,
  lifecyclePollPromise = null,
  lifecycleSequence = 0,
  generationOverlayTimer = null,
  generationStartedAt = 0,
  generationFinishedAt = null,
  lastGenerationTarget = null,
  backgroundProgressUsed = false,
  runtimeDetails = null,
  modelAccessRequest = 0,
  notificationUnread = 0,
  systemHealthNotified = false,
  runCompletionNotified = false,
  runFailed = false;
const shownKnowledgeNotices = new Set();
let generationResultSummary = null;
const $ = (id) => document.getElementById(id);
const esc = (v) =>
  String(v).replace(
    /[&<>'"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[c],
  );
function notificationMarkup(item) {
  return `<li class="notification-item ${esc(item.type)}"><strong>${esc(item.title)}</strong><p>${esc(item.message)}</p><time>${esc(item.time)}</time></li>`;
}
function addNotification(title, message, type = "info") {
  const list = $("notification-list");
  list.querySelector(".notification-empty")?.remove();
  list.insertAdjacentHTML(
    "afterbegin",
    notificationMarkup({
      title,
      message,
      type,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    }),
  );
  notificationUnread += 1;
  $("notification-count").textContent =
    notificationUnread > 99 ? "99+" : String(notificationUnread);
  $("notification-count").classList.remove("hidden");
}
function setNotificationPanel(open) {
  if (open) setProfilePanel(false);
  $("notification-panel").classList.toggle("hidden", !open);
  $("notification-bell").setAttribute("aria-expanded", String(open));
  if (open) {
    notificationUnread = 0;
    $("notification-count").classList.add("hidden");
  }
}
function setProfilePanel(open) {
  if (open) setNotificationPanel(false);
  $("profile-panel").classList.toggle("hidden", !open);
  $("profile-toggle").setAttribute("aria-expanded", String(open));
}
function showKnowledgeNotice(data) {
  const label = data.feature_name ? "suite" : data.knowledge_stage || "result";
  const key = data.memory_key || data.feature_name || label;
  if (shownKnowledgeNotices.has(key)) return;
  shownKnowledgeNotices.add(key);
  $("knowledge-notice-overlay").classList.remove("hidden");
  $("knowledge-notice-title").textContent = "Approved test knowledge reused";
  $("knowledge-notice-description").textContent = data.feature_name
    ? "This suite was retrieved from a previously validated knowledge-base entry instead of consuming a new AI generation request."
    : `These ${label} were retrieved from a previously validated knowledge-base entry instead of consuming a new AI generation request.`;
  document.body.classList.add("dialog-open");
  addNotification(
    "Knowledge base result",
    `${data.feature_name || `Validated ${label}`} was retrieved from approved organizational knowledge.`,
    "success",
  );
}
async function responseError(response) {
  let message = `Request failed (${response.status})`;
  try {
    const detail = (await response.json()).detail;
    if (detail?.requirements_validation) {
      window.dispatchEvent(
        new CustomEvent("requirements-validation", { detail: detail.requirements_validation }),
      );
      message = detail.message;
    }
    message = Array.isArray(detail)
      ? detail
          .map(
            (item) =>
              `${(item.loc || []).filter((part) => part !== "body").join(".")}: ${item.msg}`,
          )
          .join("; ")
      : typeof detail === "string"
        ? detail
        : message;
  } catch {}
  const reference = response.headers.get("x-request-id");
  const error = new Error(reference ? `${message} Reference ID: ${reference}` : message);
  error.referenceId = reference;
  return error;
}
async function api(path, body, options = {}) {
  const managed = !options.requestId && options.trackLifecycle !== false,
    requestId = options.requestId || crypto.randomUUID(),
    headers = { "Content-Type": "application/json", "X-Request-ID": requestId };
  if (managed) startLifecycleFeed(requestId);
  let completion = "Completed";
  try {
    const response = await fetch(path, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: options.signal,
    });
    if (!response.ok) throw await responseError(response);
    return response;
  } catch (error) {
    completion = error.name === "AbortError" ? "Cancelled" : "Failed";
    throw error;
  } finally {
    if (managed) {
      await stopLifecycleFeed(requestId);
      finishAgentWorkflow(completion);
    }
  }
}
async function upload(path, body, options = {}) {
  const headers = {};
  if (options.requestId) headers["X-Request-ID"] = options.requestId;
  const response = await fetch(path, { method: "POST", headers, body, signal: options.signal });
  if (!response.ok) throw await responseError(response);
  return response;
}
function showRuntimeDetails(health) {
  runtimeDetails = {
    health,
    provider: "Automatic fallback",
    model: `Copilot → ${health.openai_model} → ${health.gemini_model} → Codex`,
    auth:
      health.openai_configured || health.gemini_configured
        ? "Copilot + API key + Codex"
        : "Copilot + signed-in Codex",
  };
  syncSelectedRuntimeDetails();
  if (!systemHealthNotified) {
    addNotification(
      "System ready",
      "AI provider routing and the test-generation service are available.",
      "success",
    );
    systemHealthNotified = true;
  }
}
function syncSelectedRuntimeDetails() {
  if (!runtimeDetails) return;
  const selection = $("llm-model").value || "auto-fallback";
  const explicit = {
    codex: { provider: "Codex CLI", model: "gpt-6-astra", auth: "Codex sign-in" },
    openai: { provider: "OpenAI API", model: runtimeDetails.health.openai_model, auth: "OpenAI API key" },
    gemini: { provider: "Gemini API", model: runtimeDetails.health.gemini_model, auth: "Gemini API key" },
  };
  const detail = selection === "auto-fallback" ? runtimeDetails
    : explicit[selection] || { provider: "GitHub Copilot", model: "claude-haiku-4.5", auth: "Copilot account" };
  $("generation-llm-provider").textContent = detail.provider;
  $("generation-llm-model").textContent = detail.model;
  $("generation-llm-auth").textContent = detail.auth;
  $("generation-service-caption").textContent = `Selected route: ${detail.provider} · ${detail.model}`;
  $("model-name").textContent = detail.provider;
  $("llm-model-detail").textContent = detail.model;
  $("auth-mode").textContent = detail.auth;
}
async function loadRuntimeStatus() {
  const origin = window.MobileApp?.backend || window.location.origin;
  $("server-location").textContent = origin;
  $("flow-server").textContent = "Copilot + OpenAI + Gemini + Codex · local API";
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error();
    const health = await response.json();
    showRuntimeDetails(health);
    $("runtime-health").textContent = health.ok ? "● Service online" : "● Service unavailable";
    $("runtime-health").classList.toggle("live", Boolean(health.ok));
    $("active-agent").textContent = "Auto Finance Quality Agent";
    $("runtime-id").textContent = health.agent_runtime_id;
    $("model-name").textContent = "Automatic fallback";
    $("llm-model-detail").textContent =
      `Copilot → ${health.openai_model} → ${health.gemini_model} → Codex`;
    $("auth-mode").textContent =
      health.openai_configured || health.gemini_configured
        ? "Multi-provider credentials"
        : "Copilot + signed-in Codex";
    $("memory-status").textContent =
      `${health.organizational_memory} · ${health.organizational_memory_entries} suites`;
    syncSelectedRuntimeDetails();
  } catch {
    runtimeDetails = null;
    $("generation-llm-provider").textContent = "Unavailable";
    $("generation-llm-model").textContent = "Unavailable";
    $("generation-llm-auth").textContent = "Unavailable";
    $("runtime-health").textContent = "● Health check failed";
    $("runtime-health").classList.remove("live");
    $("active-agent").textContent = "Unavailable";
    $("runtime-id").textContent = "Unavailable";
    $("model-name").textContent = "Unavailable";
    $("llm-model-detail").textContent = "Unavailable";
    $("auth-mode").textContent = "Unavailable";
    $("memory-status").textContent = "Unavailable";
  }
}
function setWorkflowStage(stage) {
  document.querySelectorAll(".workflow-step").forEach((item, index) => {
    const current = index + 1 === stage;
    item.classList.toggle("active", current);
    item.classList.toggle("complete", index + 1 < stage);
    if (current) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  });
}
function metadataPills(items, emptyText) {
  return items?.length
    ? `<div class="metadata-pills">${items.map((item) => `<span>${esc(item)}</span>`).join("")}</div>`
    : `<p class="empty-metadata">${esc(emptyText)}</p>`;
}
function testDataMarkup(items) {
  return items?.length
    ? `<div class="test-data-grid">${items.map((item) => `<article><code>${esc(item.name)}</code><strong>${esc(item.value)}</strong><p>${esc(item.purpose)}</p></article>`).join("")}</div>`
    : '<p class="empty-metadata">No synthetic test data is required for this case.</p>';
}
function manualCaseMarkup(c) {
  return `<section class="manual-execution" aria-label="Manual execution steps"><div class="execution-heading"><div><span>Execution plan</span><h4>${c.steps.length} step${c.steps.length === 1 ? "" : "s"} to complete</h4></div><span class="human-review">Human review</span></div><section class="steps-to-reproduce"><h4>Steps to reproduce:</h4><ol>${c.steps.map((step) => `<li>${esc(step.action)}</li>`).join("")}</ol></section><section class="expected-results"><h4><span aria-hidden="true">✓</span> Expected results:</h4><ol>${c.steps.map((step) => `<li>${esc(step.expected_result)}</li>`).join("")}</ol></section><div class="manual-support-grid"><section><span class="support-label">Preconditions</span>${metadataPills(c.preconditions, "No additional preconditions")}</section><section><span class="support-label">Requirement coverage</span>${metadataPills(c.acceptance_criteria_covered, "No mapped criteria")}</section></div><details class="test-data-disclosure"><summary>Test data <span>${c.test_data.length} item${c.test_data.length === 1 ? "" : "s"}</span></summary>${testDataMarkup(c.test_data)}</details></section>`;
}
function automationCaseMarkup(c, index) {
  return `<details><summary>BDD steps & test data</summary><div class="bdd-actions"><button class="secondary copy-scenario" type="button" data-index="${index}">Copy BDD scenario</button></div><pre>${esc(c.gherkin)}</pre><h4>Test data</h4>${testDataMarkup(c.test_data)}</details>`;
}
function caseMarkup(c, index) {
  const manual = c.execution_mode === "manual" || !c.gherkin;
  if (manual)
    return `<article class="case manual-case"><input class="jira-case case-check" aria-label="Select ${esc(c.id)} for acceptance or Jira" type="checkbox" data-index="${index}" checked><details class="manual-case-accordion"><summary><span class="manual-case-heading"><small>Test case ${esc(c.id)} · Manual</small><strong>${esc(c.title)}</strong><span class="case-purpose"><b>Verifies:</b> ${esc(c.objective)}</span></span><span class="case-expand-label"><span>Expand</span><i aria-hidden="true">⌄</i></span></summary><div class="case-details"><div class="case-meta"><span class="badge">${esc(c.category)} · ${esc(c.priority)}</span></div><div class="feasibility-note"><span aria-hidden="true">◇</span><p><strong>Why this approach</strong>${esc(c.feasibility_reason)}</p></div>${manualCaseMarkup(c)}</div></details>${caseReviewMarkup(c, index)}</article>`;
  return `<article class="case automation-case"><input class="jira-case case-check" aria-label="Select ${esc(c.id)} for acceptance or Jira" type="checkbox" data-index="${index}" checked><div class="case-body"><div class="case-meta"><span class="badge">${esc(c.category)} · ${esc(c.priority)}</span><span class="case-id">Test case ${esc(c.id)} · Automation</span></div><h4 class="test-case-title">${esc(c.title)}</h4><p class="case-objective"><strong>Verifies:</strong> ${esc(c.objective)}</p><div class="feasibility-note"><span aria-hidden="true">◇</span><p><strong>Why this approach</strong>${esc(c.feasibility_reason)}</p></div>${automationCaseMarkup(c, index)}</div>${caseReviewMarkup(c, index)}</article>`;
}
function render(data) {
  resetSuiteFiles();
  executionSummary = null;
  defectDrafts = [];
  suite = data;
  $("feature").textContent = data.feature_name;
  const counts = {},
    modes = {};
  data.test_cases.forEach((c) => {
    counts[c.category] = (counts[c.category] || 0) + 1;
    modes[c.execution_mode] = (modes[c.execution_mode] || 0) + 1;
  });
  const fromKnowledge = data.generation_source === "organizational-memory",
    source = fromKnowledge ? "Knowledge reuse" : `New ${data.generation_source || "AI"} result`;
  $("summary").innerHTML =
    `<span class="chip">${esc(source)}</span>` +
    [...Object.entries(counts), ...Object.entries(modes)]
      .map(([k, v]) => `<span class="chip">${esc(k)} · ${esc(v)}</span>`)
      .join("");
  $("cases").innerHTML = data.test_cases.map(caseMarkup).join("");
  $("notes").innerHTML =
    `<h4>Source</h4><ul><li>${esc(source)}${data.memory_key ? ` · key ${esc(data.memory_key)}` : ""}</li></ul><h4>Assumptions</h4><ul>${data.assumptions.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><h4>Coverage</h4><ul>${data.coverage_notes.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  $("results").classList.remove("hidden");
  $("agent-workspace").classList.remove("hidden");
  $("agent-output").textContent = "Select an agent action to inspect its result.";
  $("metrics-dashboard-state").textContent = "AWAITING DATA";
  $("metrics-dashboard").innerHTML = "<p>Generate metrics for the current designed suite.</p>";
  syncGeneratedSuiteActions();
  setWorkflowStage(2);
  window.dispatchEvent(new CustomEvent("workspace-suite-rendered"));
  if (!activeGeneration?.background)
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  if (fromKnowledge) showKnowledgeNotice(data);
}
function elapsed(ms) {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
const generationStages = {
  "ba-review": {label: "BA review", agent: "BA Agent", title: "Reviewing BRD", message: "Assessing the BRD against available auto-finance knowledge."},
  stories: {
    label: "Story generation",
    agent: "Story Agent",
    title: "Generating stories from your requirements",
    message: "Reading your BRD and creating stories with acceptance criteria.",
  },
  scenarios: {
    label: "Scenario generation",
    agent: "Scenario Agent",
    title: "Generating test scenarios",
    message: "Building scenario coverage from your accepted stories.",
  },
  "test-cases": {
    label: "Test case generation",
    agent: "Test Case Agent",
    title: "Generating test cases",
    message: "Creating and validating test cases from your reviewed scenarios.",
  },
  "execution-plan": {
    label: "Execution planning",
    agent: "Execution Agent",
    title: "Preparing the execution plan",
    message: "Checking the configured project and preparing its feature list.",
    runtime: true,
  },
  execution: {
    label: "Test execution",
    agent: "Execution Agent",
    title: "Running test execution",
    message: "Running the configured feature files and waiting for actual test results.",
    runtime: true,
  },
};
function showGenerationOverlay(target) {
  lastGenerationTarget = target;
  stopGenerationHome.prepend($("stop-generation"));
  $("generation-progress-slot").append($("generation-progress-panel"));
  $("background-run-tray").hidden = true;
  const running = Boolean(activeGeneration) && generationFinishedAt === null;
  $("cancel-generation-overlay").hidden = !running;
  $("background-generation-label").textContent = running ? "Run in background" : "Back to progress";
  window.dispatchEvent(new CustomEvent("workspace-busy-change", { detail: { busy: running } }));
  const stories = target === "stories",
    automatic = target === "auto",
    manual = target === "manual" || target === "non_functional",
    both = target === "both";
  $("generation-agent-label").textContent = stories
    ? "Story Agent is working"
    : "DecisionAgent is working";
  $("generation-overlay-title").textContent = stories
    ? "Generating stories from your requirements"
    : automatic
      ? "Selecting the best AI specialist"
      : both
        ? "Generating combined test coverage"
        : manual
          ? target === "non_functional"
            ? "Generating non-functional test cases"
            : "Generating functional test cases"
          : "Generating automation test cases";
  $("generation-overlay-message").textContent = stories
    ? "Reading your BRD and creating source-grounded stories with acceptance criteria. You can run this in the background while keeping this page open."
    : automatic
      ? "OrchestratorAgent is analyzing your requirements and routing intent."
      : both
        ? "DecisionAgent is coordinating the Manual and Automation Specialists."
        : manual
          ? "DecisionAgent and the Manual Testing Specialist are creating review-ready steps and expected results."
          : "DecisionAgent and the Automation Specialist are creating validated BDD and automation coverage.";
  const stage = generationStages[target];
  $("cancel-generation-overlay-label").textContent = stage?.runtime
    ? "Cancel operation"
    : "Cancel generation";
  if (stage) {
    $("generation-agent-label").textContent = `${stage.agent} is working`;
    $("generation-overlay-title").textContent = stage.title;
    $("generation-overlay-message").textContent =
      `${stage.message} You can run this in the background while keeping this page open.`;
  }
  if (generationFinishedAt !== null) {
    $("generation-agent-label").textContent = generationOperation.status;
    $("generation-overlay-title").textContent = `${stage?.label || "Generation"} · ${generationOperation.status}`;
    $("generation-overlay-message").textContent = "Review the recorded agent progress and validation evidence for this operation.";
  }
  document.querySelector(".generation-agent-pulse").classList.toggle("hidden", !running);
  $("generation-overlay").querySelector(".generation-progress").classList.toggle("hidden", !running);
  document
    .querySelector(".generation-llm-details")
    .classList.toggle("hidden", Boolean(stage?.runtime));
  document.querySelector(".generation-agent-pulse").innerHTML = (
    stage?.runtime ? ["Prepare", "Run", "Results"] : ["Analyze", "Design", "Validate"]
  )
    .map((label) => `<span>${label}</span>`)
    .join("");
  if (!runtimeDetails) loadRuntimeStatus();
  if (runtimeDetails) syncSelectedRuntimeDetails();
  else $("generation-llm-model").textContent = $("llm-model").selectedOptions[0].textContent;
  $("generation-overlay").classList.remove("hidden");
  renderGenerationOverview();
  $("cancel-generation-overlay").focus();
  document.body.classList.add("dialog-open");
  if (generationOverlayTimer) clearInterval(generationOverlayTimer);
  updateGenerationClock();
  if (generationFinishedAt === null)
    generationOverlayTimer = setInterval(updateGenerationClock, 250);

}
function hideGenerationOverlay(releaseBusy = true) {
  if (releaseBusy && generationOverlayTimer) {
    clearInterval(generationOverlayTimer);
    generationOverlayTimer = null;
  }
  $("generation-overlay").classList.add("hidden");
  if ($("knowledge-notice-overlay").classList.contains("hidden"))
    document.body.classList.remove("dialog-open");
  if (releaseBusy)
    window.dispatchEvent(new CustomEvent("workspace-busy-change", { detail: { busy: false } }));
}
$("cancel-generation-overlay").onclick = () => $("stop-generation").click();
document.querySelector(".topbar").after($("background-run-tray"));
const stopGenerationHome = $("stop-generation").parentElement;
function updateGenerationClock() {
  const value = `${elapsed((generationFinishedAt ?? performance.now()) - generationStartedAt)} elapsed`;
  $("generation-overlay-time").textContent = value;
  $("background-run-time").textContent = value;
}
function updateGenerationBanner() {
  // Provider/lifecycle events report activity, not a measurable fraction of remaining work.
  generationOperation.render($("background-run-tray"), $("background-run-percent"),
    "operation", "Completion percentage is unavailable while the operation is running", true);
}

function showBackgroundProgress() {
  $("background-run-tray").dataset.compact = "true";
  $("background-run-symbol").hidden = false;
  $("background-run-percent").hidden = false;
  $("reopen-generation").textContent = "Open";
  $("dismiss-generation-progress").textContent = "×";
  $("dismiss-generation-progress").setAttribute("aria-label", "Dismiss generation progress");
  updateGenerationBanner();
  $("background-run-body").append($("generation-progress-panel"));
  stopGenerationHome.prepend($("stop-generation"));
  $("background-run-title").textContent = generationStages[lastGenerationTarget]?.label || "Generation progress";
  $("background-run-summary").textContent = generationFinishedAt === null
    ? "Running in the background. Agent updates continue below."
    : `Operation ${generationOperation.status.toLowerCase()}. Recorded progress is available below.`;
  $("dismiss-generation-progress").hidden = generationFinishedAt === null;
  $("background-run-tray").hidden = false;
}
$("background-generation-overlay").onclick = () => {
  if (activeGeneration) activeGeneration.background = true;
  backgroundProgressUsed = true;
  hideGenerationOverlay(false);
  showBackgroundProgress();
  if (activeGeneration) $("status").textContent =
    `${generationStages[activeGeneration.kind]?.label || "Generation"} continues in the background. Keep this page open; open progress to return to the pop-up.`;
  $("reopen-generation").focus({preventScroll: true});
};
$("reopen-generation").onclick = () => {
  if (activeGeneration) activeGeneration.background = false;
  showGenerationOverlay(lastGenerationTarget);
  if (!activeGeneration) $("background-generation-overlay").focus();
};
$("dismiss-generation-progress").onclick = () => { $("background-run-tray").hidden = true; };
$("notification-bell").onclick = (event) => {
  event.stopPropagation();
  setProfilePanel(false);
  setNotificationPanel($("notification-panel").classList.contains("hidden"));
};
$("profile-toggle").onclick = (event) => {
  event.stopPropagation();
  setNotificationPanel(false);
  setProfilePanel($("profile-panel").classList.contains("hidden"));
};
$("clear-notifications").onclick = () => {
  $("notification-list").innerHTML =
    '<li class="notification-empty">Run activity and system updates will appear here.</li>';
  notificationUnread = 0;
  $("notification-count").classList.add("hidden");
};
$("close-knowledge-notice").onclick = () => {
  $("knowledge-notice-overlay").classList.add("hidden");
  document.body.classList.remove("dialog-open");
};
document.addEventListener("click", (event) => {
  if (!event.target.closest(".notification-center")) setNotificationPanel(false);
  if (!event.target.closest(".profile-menu")) setProfilePanel(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    setNotificationPanel(false);
    setProfilePanel(false);
    if (!$("knowledge-notice-overlay").classList.contains("hidden"))
      $("close-knowledge-notice").click();
  }
});
function closeModelAccess() {
  $("model-access-overlay").classList.add("hidden");
}
function modelAccessRow(label, value) {
  return `<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`;
}
function modelUsageRows(result) {
  const quota = result.quota;
  const numeric = (value) => typeof value === "number" && Number.isFinite(value);
  let used = "Unavailable",
    remaining = "Unavailable",
    reset = "Unavailable";
  let scope = "Usage could not be retrieved for this check.";
  if (quota) {
    used = numeric(quota.used_requests) ? `${quota.used_requests} requests used` : "Unavailable";
    if (quota.is_unlimited) {
      remaining = "Unlimited";
    } else {
      if (numeric(quota.entitlement_requests)) used += ` / ${quota.entitlement_requests} allocated`;
      const count =
        numeric(quota.entitlement_requests) && numeric(quota.used_requests)
          ? `${Math.max(0, quota.entitlement_requests - quota.used_requests)} requests`
          : null;
      const percent = numeric(quota.remaining_percentage)
        ? `${quota.remaining_percentage.toFixed(1)}%`
        : null;
      remaining = [count, percent].filter(Boolean).join(" · ") || "Unavailable";
    }
    reset = quota.reset_date || "Not reported";
    scope = "Shared Copilot account allowance; not usage for this model or project alone.";
  } else if (result.model === "openai") {
    used = "Not provided by model access check";
    remaining = "Not provided by model access check";
    reset = "Not provided by model access check";
    scope = "View API usage and billing in the OpenAI Platform dashboard.";
  } else if (result.model === "gemini") {
    used = "Not provided by model access check";
    remaining = "Not provided by model access check";
    reset = "Not provided by model access check";
    scope = "View Gemini API usage and billing in Google AI Studio.";
  } else if (result.model === "codex") {
    used = "Not provided by CLI login status";
    remaining = "Not provided by CLI login status";
    reset = "Not provided by CLI login status";
    scope = "Sign-in status does not report account usage or remaining allowance.";
  }
  return (
    modelAccessRow("Usage", used) +
    modelAccessRow("Remaining allowance", remaining) +
    modelAccessRow("Quota reset", reset) +
    modelAccessRow("Usage scope", scope)
  );
}
function modelProviderRows(provider) {
  return (
    `<div class="model-provider-heading"><dt>${esc(provider.display_name)}</dt><dd>${esc(`${provider.can_use ? "Ready" : "Unavailable"} · ${provider.reason}`)}</dd></div>` +
    modelUsageRows(provider)
  );
}
async function checkModelAccess() {
  const select = $("llm-model"),
    model = select.value,
    request = ++modelAccessRequest,
    popup = $("model-access-overlay"),
    card = popup.querySelector(".model-access-popup");
  select.dataset.access = "checking";
  syncGenerateAvailability();
  card.classList.remove("is-allowed", "is-blocked");
  $("model-access-title").textContent = "Checking model access…";
  $("model-access-summary").textContent =
    "Verifying account permissions and usage limits without consuming a generation request.";
  $("model-access-details").innerHTML =
    modelAccessRow("Selected model", select.selectedOptions[0].textContent) +
    modelAccessRow("Status", "Checking…");
  popup.classList.remove("hidden");
  try {
    const response = await fetch(`/api/llm/models/${encodeURIComponent(model)}/access`);
    if (!response.ok) throw await responseError(response);
    const result = await response.json();
    if (request !== modelAccessRequest) return;
    select.dataset.access = result.can_use ? "allowed" : "blocked";
    card.classList.add(result.can_use ? "is-allowed" : "is-blocked");
    $("model-access-title").textContent = result.can_use
      ? "AI route available"
      : "AI route unavailable";
    $("model-access-summary").textContent = result.reason;
    const providers = result.providers || [];
    $("model-access-details").innerHTML =
      modelAccessRow("Selection", result.display_name) +
      modelAccessRow("Route / policy", result.policy) +
      (providers.length ? providers.map(modelProviderRows).join("") : modelUsageRows(result)) +
      modelAccessRow("Can generate", result.can_use ? "Yes" : "No");
    if (!result.can_use) await loadAvailableModels();
  } catch (error) {
    if (request !== modelAccessRequest) return;
    select.dataset.access = "blocked";
    card.classList.add("is-blocked");
    $("model-access-title").textContent = "Access check unavailable";
    $("model-access-summary").textContent = error.message;
    $("model-access-details").innerHTML =
      modelAccessRow("Selected model", select.selectedOptions[0].textContent) +
      modelUsageRows({ model }) +
      modelAccessRow("Can generate", "Not verified");
  } finally {
    if (request === modelAccessRequest) syncGenerateAvailability();
  }
}
$("close-model-access").onclick = closeModelAccess;
$("model-access-overlay").addEventListener("click", (event) => {
  if (event.target === $("model-access-overlay")) closeModelAccess();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("model-access-overlay").classList.contains("hidden"))
    closeModelAccess();
});
function mergeSuites(first, expanded) {
  const seen = new Set();
  const cases = [...first.test_cases, ...expanded.test_cases]
    .filter((c) => {
      const key = `${c.title}|${c.objective}`.toLowerCase().trim();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((c, i) => ({ ...c, id: `TC-${String(i + 1).padStart(3, "0")}` }));
  return {
    ...first,
    assumptions: [...new Set([...first.assumptions, ...expanded.assumptions])],
    coverage_notes: [...new Set([...first.coverage_notes, ...expanded.coverage_notes])],
    test_cases: cases,
  };
}
function syncGenerateAvailability() {
  if (typeof syncReviewControls === "function") syncReviewControls();
  const hasInput = Boolean(attachedFile || $("description").value.trim()),
    modelUnavailable = ["checking", "blocked"].includes($("llm-model").dataset.access);
  $("generate").disabled =
    Boolean(activeGeneration || generationSubmitPending) ||
    !hasInput ||
    (!document.querySelector(".stage-workspace") && modelUnavailable);
}
function setDescription(value) {
  $("description").value = value;
  window.dispatchEvent(new CustomEvent("workspace-source-replaced"));
  $("character-count").textContent = `${value.length} characters`;
  syncGenerateAvailability();
}
function showSourceChoices() {
  $("jira-link-panel").classList.add("hidden");
  $("show-jira-link").classList.remove("hidden");
}
function setSourceMenu(open) {
  $("requirement-source-menu").classList.toggle("hidden", !open);
  $("add-requirement-source").setAttribute("aria-expanded", String(open));
  if (open) {
    showSourceChoices();
    $("requirement-source-menu").querySelector("label,button")?.focus();
  }
}
$("add-requirement-source").onclick = () =>
  setSourceMenu($("requirement-source-menu").classList.contains("hidden"));
$("close-requirement-source").onclick = () => setSourceMenu(false);
$("show-jira-link").onclick = () => {
  $("show-jira-link").classList.add("hidden");
  $("jira-link-panel").classList.remove("hidden");
  $("jira-source-key").focus();
};
$("jira-link-back").onclick = () => {
  showSourceChoices();
  $("show-jira-link").focus();
};
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setSourceMenu(false);
});
document.addEventListener("click", (event) => {
  if (
    !$("requirement-source-menu").classList.contains("hidden") &&
    !event.target.closest(".textarea-wrap")
  )
    setSourceMenu(false);
});
const validationEvidence = new Map();
function recordOperationResult(stage, result) {
  const counts = {
    stories: result.stories?.length,
    scenarios: result.scenarios?.length,
    "test-cases": result.suite?.test_cases?.length,
    "execution-plan": result.cases?.length,
  };
  const labels = { stories: "stories", scenarios: "scenarios", "test-cases": "test cases", "execution-plan": "planned cases" };
  generationResultSummary = {
    stage,
    output: stage === "ba-review" ? `Review: ${String(result.outcome).replaceAll("_", " ")}`
      : stage === "execution" ? `Run: ${result.status || "reported"}`
      : counts[stage] !== undefined ? `${counts[stage]} ${labels[stage]}` : "Result available",
    next: stage === "ba-review" ? result.outcome === "ready_for_business_review"
      ? "Review the BA findings before confirming the requirements and creating stories."
      : "Review the findings and resolve open questions before continuing."
      : stage === "stories" ? "Review and accept the stories to create scenarios."
      : stage === "scenarios" ? "Review and accept the scenarios to create test cases."
      : stage === "execution-plan" ? "Review the plan and runtime prerequisites before starting execution."
      : stage === "execution" ? "Review the runner-reported results and any failures in the Execution stage."
      : result.validation?.passed === false ? "Resolve the validation findings before accepting the test cases."
      : "Review and accept the test cases before building automation or recording execution.",
  };
  renderGenerationOverview();
}
function renderGenerationOverview() {
  const finished = generationFinishedAt !== null;
  $("generation-overview-status").textContent = finished ? generationOperation.status : "In progress";
  $("generation-overview-output").textContent = generationResultSummary?.output || "Not available";
  const statuses = [...validationEvidence.values()].map((entry) => entry.status);
  $("generation-overview-validation").textContent = !statuses.length
    ? finished ? "Not reported" : "Not reported yet"
    : statuses.includes("failed") || statuses.includes("blocked") ? "Needs attention"
    : statuses.every((value) => ["passed", "aligned"].includes(value)) ? "Reported checks passed"
    : statuses.every((value) => value === "pending") ? finished ? "Result not reported" : "Awaiting result"
    : "Results reported";
  $("generation-next-step").textContent = finished
    ? generationOperation.status === "Completed" ? generationResultSummary?.next || "Review the operation output and recorded evidence."
      : generationOperation.status === "Cancelled" ? "The operation was cancelled. Review any retained output before retrying."
      : "The operation stopped with an error. Open the activity log for details before retrying."
    : "Keep this page open. You can continue in the background or cancel the operation.";
  $("generation-view-result").hidden = !finished || !generationResultSummary;
  $("generation-activity-count").textContent = `${$("generation-background-events").querySelectorAll("li:not(.empty-event)").length} updates`;
}
$("generation-view-result").addEventListener("click", () => {
  const stage = generationResultSummary?.stage;
  const view = stage === "ba-review" ? "requirements" : stage === "execution-plan" ? "execution" : stage;
  hideGenerationOverlay();
  $("background-run-tray").hidden = true;
  if (view && window.navigateWorkspace) window.navigateWorkspace(window.workflowStageUrl(view), false);
  const target = stage === "ba-review" ? $("ba-report") : $("stage-panel-" + ({ stories: 2, scenarios: 3, "test-cases": 4, execution: 5, "execution-plan": 5 }[stage] || 4));
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
});
function renderValidationEvidence(event) {
  if (!["validation_basis", "validation_source"].includes(event.action)) return;
  if (event.action === "validation_basis") {
    validationEvidence.set(event.agent, {
      basis: event.summary,
      status: event.status,
      sources: [],
    });
  } else {
    if (!validationEvidence.has(event.agent))
      validationEvidence.set(event.agent, {
        basis: "Validation result not reported.",
        status: "pending",
        sources: [],
      });
    validationEvidence.get(event.agent).sources.push(event.summary);
  }
  paintValidationEvidence();
}
function paintValidationEvidence() {
  renderGenerationOverview();
  if (!validationEvidence.size) {
    $("generation-validation-evidence").textContent = generationFinishedAt === null
      ? "Waiting for validation evidence. No checks have been reported yet."
      : "No validation evidence was reported before this operation ended. Completion alone does not establish that checks passed.";
    return;
  }
  $("generation-validation-evidence").innerHTML = [...validationEvidence.entries()]
    .map(
      ([agent, evidence]) =>
        `<article><h4>${esc(agent)} · ${esc(evidence.status === "pending" && generationFinishedAt !== null ? "result not reported" : evidence.status)}</h4><p>${esc(evidence.basis)}</p><strong>Reference knowledge sources</strong>${evidence.sources.length ? `<ul>${evidence.sources.map((source) => `<li>${esc(source)}</li>`).join("")}</ul>` : `<p>${generationFinishedAt === null ? "Waiting for source references…" : "No source references were reported for this check."}</p>`}</article>`,
    )
    .join("");
}
function recordReturnedEvidence(agent, status, basis, sources = [], replace = false) {
  const existing = validationEvidence.get(agent);
  if (existing && existing.status !== "pending" && !replace) return;
  if (existing?.status === "pending") sources = [...new Set([...existing.sources, ...sources])];
  validationEvidence.set(agent, { status, basis, sources });
  paintValidationEvidence();
}
function recordSuiteValidation(report, generated) {
  if (!report) return;
  recordReturnedEvidence("Quality Gate", report.passed ? "passed" : "failed",
    `Returned design-validation report: ${report.passed ? "passed" : "failed"}, score ${report.score}/100. Recognized criteria covered: ${report.acceptance_criteria_covered ?? "not reported"}/${report.acceptance_criteria_total ?? "not reported"}. ${(report.findings || []).length} findings returned. This is not test execution or business approval.`,
    [`Returned suite: ${generated?.feature_name || "unnamed"}. Case IDs: ${(generated?.test_cases || []).map((c) => c.id).join(", ") || "none"}. Detailed live checkpoints may be unavailable.`],
    validationEvidence.has("Quality Gate") && validationEvidence.get("Quality Gate").status !== (report.passed ? "passed" : "failed"));
}
const lifecycleWaitingRows = new Map();
function resetLifecycleFeed() {
  generationResultSummary = null;
  $("generation-activity-count").textContent = "0 updates";
  document.querySelector(".generation-activity-details").open = false;
  document.querySelector(".generation-validation").open = false;
  document.querySelector(".generation-request-details").open = false;
  lifecycleWaitingRows.clear();
  validationEvidence.clear();
  $("generation-validation-evidence").innerHTML =
    "<p>Waiting for validation evidence. No checks have been reported yet.</p>";
  $("live-agent-events").innerHTML = "";
  $("generation-background-events").innerHTML =
    '<li class="empty-event">Waiting for the first agent update…</li>';
  $("live-agent-feed-state").textContent = "RUNNING";
  $("generation-background-state").textContent = "RUNNING";
  lifecycleSequence = 0;
  runCompletionNotified = false;
  runFailed = false;
  $("generation-current-agent").textContent = "Preparing request";
  $("generation-current-activity").textContent = "Waiting for backend activity. The request may still be preparing its source and knowledge context.";
  $("generation-feed-health").textContent = "Connecting to backend activity…";
}
function lifecycleItem(event) {
  if (event.status === "failed") runFailed = true;
  const item = document.createElement("li");
  item.className = event.status;
  const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : "";
  const label = event.action === "provider_wait" ? "waiting update"
    : ["running", "started"].includes(event.status) ? "started" : event.status;
  item.innerHTML = `<strong>${esc(event.agent)}</strong><p>${esc(event.summary)}</p><em>${esc(label)} · ${esc((event.action || "activity").replaceAll("_", " "))}${time ? ` · ${esc(time)}` : ""}</em>`;
  return item;
}
function renderLifecycleRow(event) {
  const live = lifecycleItem(event), background = lifecycleItem(event);
  if (event.action === "provider_wait") {
    const key = event.summary.replace(/\(\d+s elapsed\)/g, "(elapsed)");
    const previous = lifecycleWaitingRows.get(event.agent);
    if (previous?.key === key) {
      previous.live.replaceWith(live);
      previous.background.replaceWith(background);
    } else {
      $("live-agent-events").append(live);
      $("generation-background-events").append(background);
    }
    lifecycleWaitingRows.set(event.agent, { key, live, background });
    return;
  }
  if (event.action?.startsWith("provider_")) lifecycleWaitingRows.delete(event.agent);
  $("live-agent-events").append(live);
  $("generation-background-events").append(background);
}
function renderLifecycleEvents(events) {
  events.forEach((event) => {
    if (event.sequence <= lifecycleSequence) return;
    $("generation-background-events").querySelector(".empty-event")?.remove();
    lifecycleSequence = event.sequence;
    $("generation-current-agent").textContent = event.agent;
    $("generation-current-activity").textContent = event.summary;
    $("generation-feed-health").textContent = event.timestamp
      ? `Last backend update: ${new Date(event.timestamp).toLocaleTimeString()}` : "Backend activity received";
    renderValidationEvidence(event);
    updateAgentWorkflow(event);
    updateGenerationBanner(event);
    renderLifecycleRow(event);
  });
  $("live-agent-events").scrollTop = $("live-agent-events").scrollHeight;
  $("generation-background-events").scrollTop = $("generation-background-events").scrollHeight;
  renderGenerationOverview();
}
async function pollLifecycle(requestId) {
  if (requestId !== activeLifecycleRequestId) return;
  if (lifecyclePollPromise) return lifecyclePollPromise;
  const poll = (async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(
        `/api/generation/${encodeURIComponent(requestId)}/events?after=${lifecycleSequence}`,
        { signal: controller.signal },
      );
      if (!response.ok) throw new Error(`Activity feed returned ${response.status}`);
      const data = await response.json();
      if (requestId !== activeLifecycleRequestId) return;
      renderLifecycleEvents(data.events || []);
      if (lifecycleSequence && !data.events?.length && $("generation-feed-health").textContent.includes("temporarily unavailable"))
        $("generation-feed-health").textContent = "Live activity reconnected. Waiting for the next backend update.";
      if (!lifecycleSequence)
        $("generation-feed-health").textContent = data.complete
          ? "Backend finished without reporting activity." : "Connected. Waiting for the backend to report its first activity.";
      if (data.complete) {
        $("live-agent-feed-state").textContent = "COMPLETE";
        $("generation-background-state").textContent = "COMPLETE";
      }
    } catch {
      if (requestId === activeLifecycleRequestId)
        $("generation-feed-health").textContent = "Live activity temporarily unavailable. Retrying; the operation may still be running.";
    } finally {
      clearTimeout(timeout);
    }
  })();
  lifecyclePollPromise = poll;
  try {
    await poll;
  } finally {
    if (lifecyclePollPromise === poll) lifecyclePollPromise = null;
  }
}
function startLifecycleFeed(requestId) {
  if (activeLifecycleTimer) clearInterval(activeLifecycleTimer);
  activeLifecycleRequestId = requestId;
  lifecyclePollPromise = null;
  generationStartedAt = performance.now();
  generationFinishedAt = null;
  generationOperation.reset();
  backgroundProgressUsed = false;
  $("background-run-tray").hidden = true;
  $("generation-progress-slot").append($("generation-progress-panel"));
  resetLifecycleFeed();
  $("generation-activity-log").href = `/logs?request_id=${encodeURIComponent(requestId)}&view=activity`;
  $("generation-request-reference").textContent = requestId;
  beginAgentWorkflow(activeGeneration?.kind || null);
  addNotification(
    "Generation started",
    activeGeneration?.kind === "stories"
      ? "Your requirements are being converted into stories."
      : generationStages[activeGeneration?.kind]?.message || "An agent operation is now processing.",
  );
  pollLifecycle(requestId);
  activeLifecycleTimer = setInterval(() => pollLifecycle(requestId), 500);
}
async function stopLifecycleFeed(requestId) {
  if (requestId !== activeLifecycleRequestId) return;
  if (activeLifecycleTimer) clearInterval(activeLifecycleTimer);
  activeLifecycleTimer = null;
  if (lifecyclePollPromise) await lifecyclePollPromise;
  if (requestId !== activeLifecycleRequestId) return;
  await pollLifecycle(requestId);
  if (requestId !== activeLifecycleRequestId) return;
  activeLifecycleRequestId = null;
  if ($("live-agent-feed-state").textContent === "RUNNING")
    $("live-agent-feed-state").textContent = "STOPPED";
  if ($("generation-background-state").textContent === "RUNNING")
    $("generation-background-state").textContent = "STOPPED";
}
const requirementPlaceholder = $("description").getAttribute("placeholder") || "";
function showFile(file) {
  attachedFile = file;
  setDescription("");
  $("description").setAttribute("placeholder", "");
  $("file-preview").classList.remove("hidden");
  $("file-type").textContent = (file.name.split(".").pop() || "file").toUpperCase();
  $("file-name").textContent = file.name;
  $("file-size").textContent =
    file.size < 1048576
      ? `${Math.max(1, Math.round(file.size / 1024))} KB`
      : `${(file.size / 1048576).toFixed(1)} MB`;
  $("source-state").textContent = "Document attached · ready to read";
  $("description").closest(".textarea-wrap").classList.add("has-attachment");
  $("status").textContent = `${file.name} attached. Select Generate stories when ready.`;
  syncGenerateAvailability();
  setSourceMenu(false);
}
function clearFile() {
  attachedFile = null;
  $("requirement-file").value = "";
  $("description").setAttribute("placeholder", requirementPlaceholder);
  $("file-preview").classList.add("hidden");
  $("source-state").textContent = "";
  $("description").closest(".textarea-wrap").classList.remove("has-attachment");
  syncGenerateAvailability();
}
const businessRulesPlaceholder = $("business-rules").getAttribute("placeholder") || "";
let attachedBusinessRulesFile = null;
function parseBusinessRules() {
  const seen = new Set(),
    rules = [];
  for (const [index, line] of $("business-rules").value.split("\n").entries()) {
    const value = line.trim();
    if (!value) continue;
    const match = value.match(/^(BR-[A-Za-z0-9_-]+)\s*:\s*(.{3,})$/i);
    if (!match) throw new Error(`Rule line ${index + 1} must use BR-ID: description.`);
    const id = match[1].toUpperCase();
    if (seen.has(id)) throw new Error(`Business rule ${id} is duplicated.`);
    seen.add(id);
    rules.push({ id, description: match[2].trim() });
  }
  if (rules.length > 100) throw new Error("A maximum of 100 business rules can be supplied.");
  return rules;
}
function showBusinessRulesFile(file) {
  attachedBusinessRulesFile = file;
  $("business-rules").value = "";
  $("business-rules").setAttribute("placeholder", "");
  $("rule-file-preview").classList.remove("hidden");
  $("rule-file-type").textContent = (file.name.split(".").pop() || "file").toUpperCase();
  $("rule-file-name").textContent = file.name;
  $("rule-file-size").textContent =
    file.size < 1048576
      ? `${Math.max(1, Math.round(file.size / 1024))} KB`
      : `${(file.size / 1048576).toFixed(1)} MB`;
  $("business-rules").closest(".rule-textarea-wrap").classList.add("has-attachment");
  $("rule-count").textContent = "Document attached";
  $("rule-save-state").textContent = "Processed when you generate";
}
function clearBusinessRulesFile() {
  attachedBusinessRulesFile = null;
  $("business-rules-file").value = "";
  $("business-rules").setAttribute("placeholder", businessRulesPlaceholder);
  $("rule-file-preview").classList.add("hidden");
  $("business-rules").closest(".rule-textarea-wrap").classList.remove("has-attachment");
  syncBusinessRuleCount();
}
async function saveSharedRules(options = {}) {
  await sharedRulesReady;
  let rules = parseBusinessRules();
  if (attachedBusinessRulesFile) {
    const form = new FormData();
    form.append("file", attachedBusinessRulesFile);
    const response = await upload("/api/business-rules/document", form, options);
    rules = (await response.json()).business_rules;
  }
  const response = await fetch("/api/workspace/rules", {
    method: "PUT",
    signal: options.signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ business_rules: rules }),
  });
  if (!response.ok) throw await responseError(response);
  $("rule-save-state").textContent = `Saved ${rules.length} shared rules`;
  if (attachedBusinessRulesFile) {
    clearBusinessRulesFile();
    $("business-rules").value = rules.map((r) => `${r.id}: ${r.description}`).join("\n");
  }
  return rules;
}
async function resolveBusinessRules(options = {}) {
  if (options.persistShared === false) {
    await sharedRulesReady;
    if (attachedBusinessRulesFile) {
      const form = new FormData(); form.append("file", attachedBusinessRulesFile);
      const response = await upload("/api/business-rules/document", form, options);
      const rules = (await response.json()).business_rules;
      clearBusinessRulesFile();
      $("business-rules").value = rules.map((rule) => `${rule.id}: ${rule.description}`).join("\n");
    }
    $("rule-save-state").textContent = "Rules included in this project source; shared rules unchanged";
    return parseBusinessRules();
  }
  await saveSharedRules(options);
  return [];
}

function syncBusinessRuleCount() {
  const count = $("business-rules")
    .value.split("\n")
    .filter((line) => line.trim()).length;
  $("rule-count").textContent = `${count} rule${count === 1 ? "" : "s"}`;
  $("rule-save-state").textContent = "Unsaved changes";
}
const sharedRulesReady = (async () => {
  if (document.body.dataset.guest === "true") return;
  const response = await fetch("/api/workspace/rules");
  if (!response.ok) throw await responseError(response);
  const data = await response.json();
  $("business-rules").value = data.business_rules
    .map((r) => `${r.id}: ${r.description}`)
    .join("\n");
  syncBusinessRuleCount();
  $("rule-save-state").textContent = "Shared rules loaded";
})();
sharedRulesReady.catch((error) => {
  $("rule-save-state").textContent = error.message;
});
$("business-rules").addEventListener("input", syncBusinessRuleCount);
$("save-business-rules").onclick = async () => {
  try {
    await saveSharedRules();
  } catch (error) {
    $("rule-save-state").textContent = error.message;
  }
};
$("clear-business-rules").onclick = () => {
  clearBusinessRulesFile();
  $("business-rules").value = "";
  syncBusinessRuleCount();
  $("rule-save-state").textContent = "Cleared editor; save to update shared rules";
};
$("business-rules-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) showBusinessRulesFile(file);
});
$("rule-file-remove").onclick = (event) => {
  event.preventDefault();
  clearBusinessRulesFile();
};
function jiraIssueKey(value) {
  const match = value.trim().match(/(?:\/browse\/|^)([A-Za-z][A-Za-z0-9_]*-\d+)(?:[/?#]|$)/i);
  return match?.[1]?.toUpperCase() || "";
}
$("load-jira").onclick = async () => {
  const key = jiraIssueKey($("jira-source-key").value);
  if (!key) return alert("Enter a Jira issue key or paste a valid Jira browse link.");
  const button = $("load-jira");
  button.disabled = true;
  button.textContent = "Connecting…";
  try {
    const response = await fetch(`/api/jira/issues/${encodeURIComponent(key)}/requirements`);
    if (!response.ok) throw await responseError(response);
    const requirement = await response.json();
    const sections = [`Jira story ${requirement.issue_key}: ${requirement.summary}`];
    if (requirement.description) sections.push(`Description:\n${requirement.description}`);
    if (requirement.acceptance_criteria.length)
      sections.push(
        `Acceptance criteria:\n${requirement.acceptance_criteria.map((item, index) => `AC-${String(index + 1).padStart(3, "0")}: ${item}`).join("\n")}`,
      );
    clearFile();
    setDescription(sections.join("\n\n"));
    $("source-state").textContent = `${requirement.issue_key} connected`;
    $("status").textContent =
      `Loaded ${requirement.issue_key} with ${requirement.acceptance_criteria.length} acceptance criteria. Review it, then generate the suite.`;
    setSourceMenu(false);
  } catch (error) {
    $("status").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Connect";
  }
};
$("requirement-file").addEventListener("change", (e) => {
  if (e.target.files[0]) showFile(e.target.files[0]);
});
$("file-remove").addEventListener("click", (e) => {
  e.preventDefault();
  e.stopPropagation();
  clearFile();
});
["dragenter", "dragover"].forEach((name) =>
  $("upload-zone").addEventListener(name, (e) => {
    e.preventDefault();
    $("upload-zone").classList.add("dragging");
  }),
);
["dragleave", "drop"].forEach((name) =>
  $("upload-zone").addEventListener(name, (e) => {
    e.preventDefault();
    $("upload-zone").classList.remove("dragging");
  }),
);
$("upload-zone").addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) showFile(file);
});
$("generate-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (generationSubmitPending || activeGeneration) return;
  generationSubmitPending = true;
  syncGenerateAvailability();
  const selectedFile = attachedFile,
    description = $("description").value.trim();
  if (!selectedFile && description.length < 10) {
    $("status").textContent = "Paste at least 10 characters or select a supported document.";
    generationSubmitPending = false;
    syncGenerateAvailability();
    return;
  }
  let businessRules;
  try {
    businessRules = await resolveBusinessRules();
  } catch (error) {
    $("status").textContent = error.message;
    $("rule-control").open = true;
    generationSubmitPending = false;
    syncGenerateAvailability();
    return;
  }
  setWorkflowStage(1);
  const requestId = crypto.randomUUID(),
    controller = new AbortController();
  activeGeneration = { requestId, controller, cancelled: false };
  startLifecycleFeed(requestId);
  syncGenerateAvailability();
  $("stop-generation").classList.remove("hidden");
  const start = performance.now();
  $("timer").classList.remove("hidden");
  $("timer").textContent = "00:00";
  const ticker = setInterval(
    () => ($("timer").textContent = elapsed(performance.now() - start)),
    250,
  );
  const generationTarget = selectedGenerationTarget(),
    format = generationTarget === "manual" ? "normal" : "bdd",
    manualTestingType = $("manual-testing-type").value,
    llmModel = $("llm-model").value;
  showGenerationOverlay($("output-target").value);
  let generationOutcome = "Completed";
  try {
    $("status").textContent = selectedFile
      ? "The Input Agent is preparing the document…"
      : "The Knowledge Agent is checking for an approved match…";
    let generated,
      validation = null,
      trace = [],
      options = { requestId, signal: controller.signal };
    if (selectedFile) {
      const form = new FormData();
      form.append("file", selectedFile);
      form.append("output_format", format);
      form.append("generation_target", generationTarget);
      form.append("manual_testing_type", manualTestingType);
      form.append("llm_model", llmModel);
      form.append(
        "business_rules",
        businessRules.map((rule) => `${rule.id}: ${rule.description}`).join("\n"),
      );
      form.append(
        "finance_calculation",
        window.financeCalculationContext?.()
          ? JSON.stringify(window.financeCalculationContext())
          : "",
      );
      form.append("finance_product_id", $("finance-domain-product")?.value || "");
      form.append("finance_journey_ids", $("finance-domain-journey")?.value || "");
      const response = await upload("/api/generate/document", form, options);
      const result = await response.json();
      generated = result.suite;
      validation = result.validation;
      trace = result.trace || [];
      reviewSourceRequest = result.source_request || null;
    } else {
      const response = await api(
        "/api/agent/run",
        {
          description,
          output_format: format,
          generation_target: generationTarget,
          manual_testing_type: manualTestingType,
          llm_model: llmModel,
          business_rules: businessRules,
          finance_calculation: window.financeCalculationContext?.() || null,
          finance_product_id: $("finance-domain-product")?.value || null,
          finance_journey_ids: $("finance-domain-journey")?.value
            ? [$("finance-domain-journey").value]
            : [],
        },
        options,
      );
      const result = await response.json();
      generated = result.suite;
      validation = result.validation;
      trace = result.trace || [];
      reviewSourceRequest = result.source_request || null;
    }
    validationReport = validation;
    recordOperationResult("test-cases", { suite: generated, validation });
    recordSuiteValidation(validation, generated);
    render(generated);
    const validationText = validation
      ? ` Validation: ${validation.passed ? "passed" : "needs review"} (${validation.score}/100).`
      : "";
    const traceText = trace.length ? ` Agent used ${trace.length} tool actions.` : "";
    $("status").textContent =
      `Suite ready with ${generated.test_cases.length} scenarios. ${validationText} ${traceText}`;
    $("timer").textContent = `COMPLETE · ${elapsed(performance.now() - start)}`;
    loadRuntimeStatus();
  } catch (err) {
    generationOutcome = activeGeneration?.cancelled ? "Cancelled" : "Failed";
    if (activeGeneration?.cancelled) {
      $("status").textContent = `Generation stopped. Reference ID: ${requestId}`;
    } else {
      $("status").textContent = err.message;
    }
    $("timer").textContent = `STOPPED · ${elapsed(performance.now() - start)}`;
  } finally {
    clearInterval(ticker);
    await stopLifecycleFeed(requestId);
    finishAgentWorkflow(generationOutcome);
    activeGeneration = null;
    generationSubmitPending = false;
    syncGenerateAvailability();
    $("stop-generation").classList.add("hidden");
    hideGenerationOverlay();
  }
});
$("stop-generation").onclick = async () => {
  if (!activeGeneration) return;
  if (activeGeneration.cancel) return activeGeneration.cancel();
  activeGeneration.cancelled = true;
  $("stop-generation").disabled = true;
  $("status").textContent = "Stopping generation and closing the Copilot session…";
  try {
    await fetch(`/api/generation/${encodeURIComponent(activeGeneration.requestId)}/cancel`, {
      method: "POST",
    });
  } finally {
    activeGeneration.controller.abort();
    $("stop-generation").disabled = false;
  }
};
function download(blob, name) {
  if (window.MobileApp?.native) return window.MobileApp.saveFile(blob, name);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
async function copyText(value, label) {
  try {
    await navigator.clipboard.writeText(value);
    $("status").textContent = `${label} copied to clipboard.`;
    $("status").classList.add("copy-feedback");
    setTimeout(() => $("status").classList.remove("copy-feedback"), 1400);
  } catch {
    $("status").textContent =
      "Clipboard access was blocked. Select and copy the Gherkin text manually.";
  }
}
$("cases").addEventListener("click", (e) => {
  const button = e.target.closest(".copy-scenario");
  if (button && suite)
    copyText(suite.test_cases[Number(button.dataset.index)].gherkin, "BDD scenario");
});
$("select-all").onclick = () =>
  document.querySelectorAll(".jira-case").forEach((b) => (b.checked = true));
$("select-none").onclick = () =>
  document.querySelectorAll(".jira-case").forEach((b) => (b.checked = false));
function selectedCaseIds() {
  return [...document.querySelectorAll(".jira-case:checked")].map(
    (b) => suite.test_cases[Number(b.dataset.index)].id,
  );
}
function setReviewerError(show) {
  $("accepted-by").classList.toggle("invalid", show);
  $("accepted-by").setAttribute("aria-invalid", String(show));
  $("reviewer-error").classList.toggle("hidden", !show);
}
function resetAcceptance() {
  $("review-state").textContent = "Review required";
  $("review-state").classList.remove("accepted");
  $("acceptance-receipt").classList.add("hidden");
  $("acceptance-receipt").innerHTML = "";
  setReviewerError(false);
}
$("accepted-by").addEventListener("input", (event) => {
  if (event.target.value.trim().length >= 2) setReviewerError(false);
});
$("accept-selected").onclick = async () => {
  if (!suite || !validationReport) return alert("Generate and validate a suite first.");
  const selected = selectedCaseIds(),
    acceptedBy = $("accepted-by").value.trim();
  if (!selected.length) return alert("Select at least one reviewed test case.");
  if (acceptedBy.length < 2) {
    setReviewerError(true);
    $("accepted-by").focus();
    return;
  }
  setReviewerError(false);
  const button = $("accept-selected");
  button.disabled = true;
  button.textContent = "Approving…";
  try {
    const response = await api("/api/output/accept", {
      suite,
      validation: validationReport,
      selected_case_ids: selected,
      manual_format: "xlsx",
      accepted_by: acceptedBy,
      workflow_context: window.workflowApprovalContext?.() || null,
    });
    const receipt = await response.json();
    $("review-state").textContent = "Approved";
    $("review-state").classList.add("accepted");
    $("acceptance-receipt").classList.remove("hidden");
    $("acceptance-receipt").innerHTML =
      `<strong>${receipt.selected_case_ids.length} cases approved</strong><span>Stored in ${esc(receipt.output_directory)}</span><ul>${receipt.artifacts.map((item) => `<li>${esc(item.filename)} · ${item.case_count} case${item.case_count === 1 ? "" : "s"}</li>`).join("")}</ul>`;
    setWorkflowStage(4);
  } catch (err) {
    alert(err.message);
  } finally {
    button.disabled = false;
    button.textContent = "✓ Approve selected";
  }
};
function setJiraKeyError(show) {
  $("jira-key").classList.toggle("invalid", show);
  $("jira-key").setAttribute("aria-invalid", String(show));
  $("jira-key-error").classList.toggle("hidden", !show);
}
$("jira-key").addEventListener("input", (event) => {
  if (/^[A-Za-z][A-Za-z0-9_]*-\d+$/.test(event.target.value.trim())) setJiraKeyError(false);
});
$("jira").onclick = async () => {
  const key = $("jira-key").value.trim();
  if (!/^[A-Za-z][A-Za-z0-9_]*-\d+$/.test(key)) {
    setJiraKeyError(true);
    $("jira-key").focus();
    return;
  }
  setJiraKeyError(false);
  const selected = selectedCaseIds();
  if (!selected.length) return alert("Select at least one test case.");
  $("jira").disabled = true;
  try {
    const r = await api("/api/jira/publish", {
      issue_key: key,
      suite,
      selected_case_ids: selected,
      add_comment: true,
    });
    const result = await r.json();
    setWorkflowStage(4);
    alert(`Published ${selected.length} selected cases to ${result.issue_key}`);
  } catch (err) {
    alert(err.message);
  } finally {
    $("jira").disabled = false;
  }
};
function showAgentOutput(title, content) {
  $("agent-output").innerHTML = `<strong>${esc(title)}</strong>${content}`;
}
$("show-rule-coverage").onclick = () => {
  if (!suite) return;
  const rules = [
    ...new Set(
      suite.test_cases
        .flatMap((c) => c.acceptance_criteria_covered)
        .filter((id) => id.toUpperCase().startsWith("BR-")),
    ),
  ];
  showAgentOutput(
    "Business rule coverage",
    rules.length
      ? `<ul>${rules.map((rule) => `<li>${esc(rule)} · traced to generated tests</li>`).join("")}</ul>`
      : "<p>No explicit BR identifiers were detected in the generated suite.</p>",
  );
};
$("show-knowledge").onclick = () => {
  if (!suite) return;
  showAgentOutput(
    "Knowledge source",
    `<p>${suite.generation_source === "organizational-memory" ? "Exact validated suite recalled without a new Copilot request." : "Newly generated suite; validated knowledge is retained for an exact future match."}</p>${suite.memory_key ? `<code>${esc(suite.memory_key)}</code>` : ""}`,
  );
};
$("generate-metrics").onclick = () => window.renderStlcReport();
function syncGeneratedSuiteActions() {
  const hasSuite = Boolean(suite?.test_cases.length);
  document.querySelectorAll(".lifecycle-action").forEach((button) => (button.disabled = !hasSuite));
  $("lifecycle-guidance").textContent = hasSuite
    ? "Inspect source-rule coverage, traceability gaps, design quality and STLC readiness for the current suite."
    : "Generate a suite to view requirement traceability and STLC reporting.";
  syncSuiteFileActions();
  window.renderStlcReport?.();
}

function groupRenderedCases() {
  const container = $("cases");
  if (!suite || container.querySelector(".scenario-case-group")) return;
  const cases = [...container.querySelectorAll(":scope > .case")];
  if (!cases.length) return;
  const groups = new Map();
  cases.forEach((card) => {
    const index = Number(card.querySelector(".case-check")?.dataset.index);
    const name =
      suite.test_cases[index]?.scenario_group?.trim() || suite.feature_name || "General scenario";
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(card);
  });
  groups.forEach((cards, name) => {
    const section = document.createElement("section");
    section.className = "scenario-case-group";
    const heading = document.createElement("div");
    heading.className = "scenario-group-heading";
    const title = document.createElement("h3");
    const label = document.createElement("small");
    label.className = "scenario-label";
    label.textContent = "Business scenario";
    const headingText = document.createElement("div");
    title.textContent = name;
    headingText.append(label, title);
    const count = document.createElement("span");
    count.textContent = `${cards.length} test case${cards.length === 1 ? "" : "s"}`;
    heading.append(headingText, count);
    section.append(heading, ...cards);
    container.append(section);
  });
}
new MutationObserver(() => {
  syncGeneratedSuiteActions();
  resetAcceptance();
  groupRenderedCases();
}).observe($("cases"), { childList: true });
new MutationObserver(() => {
  const chip = $("summary").querySelector(".chip");
  if (chip && suite && suite.generation_source !== "organizational-memory")
    chip.textContent = `New ${suite.generation_source} result`;
}).observe($("summary"), { childList: true });
function renderStepDefinitions(artifact) {
  stepDefinitionArtifact = artifact;
  $("step-definition-files").innerHTML = artifact.files
    .map(
      (file, index) =>
        `<article class="step-definition-file"><div><strong>${esc(file.path)}</strong><button class="secondary copy-step-definition" type="button" data-index="${index}">Copy</button></div><pre><code>${esc(file.content)}</code></pre></article>`,
    )
    .join("");
  const coverage = artifact.coverage
    .map(
      (item) =>
        `<li><span class="coverage-status">${esc(item.status)}</span> ${esc(item.gherkin_step)} → <code>${esc(item.binding)}</code></li>`,
    )
    .join("");
  const notes = artifact.notes.map((note) => `<li>${esc(note)}</li>`).join("");
  $("step-definition-coverage").innerHTML =
    `<h4>Coverage</h4><ul>${coverage || "<li>No coverage details returned.</li>"}</ul><h4>Notes</h4><ul>${notes || "<li>No additional notes.</li>"}</ul>`;
  $("step-definitions").classList.remove("hidden");
  setWorkflowStage(3);
  $("step-definitions").scrollIntoView({ behavior: "smooth", block: "start" });
}
let agentWorkflowRun = null;
function renderAgentWorkflow() {
  const run = agentWorkflowRun;
  const badge = document.querySelector(".agent-route-badge");
  const context = document.querySelector(".agent-route-orchestrator");
  badge.textContent = run ? run.status : "Ready";
  badge.dataset.status = run?.status || "ready";
  context.textContent = run ? run.status === "Running"
    ? "Updates reported by the running agents" : "Recorded activity for this finished operation"
    : "Choose an action in Requirements";
  $("agent-workflow-summary").textContent = run
    ? generationStages[run.kind]?.label || "Agent operation"
    : "Review the BRD or generate stories from the shared requirement source.";
  const steps = run ? [...run.agents.values()] : [
    {agent: "Review requirements", summary: "Senior business analyst reviews scope, domain knowledge and testability.", status: "Available"},
    {agent: "Generate stories", summary: "Story Agent creates source-grounded stories and acceptance criteria.", status: "Available"},
  ];
  $("agent-workflow-steps").innerHTML = steps.length ? steps.map((event, index) => {
    const timestamp = event.timestamp ? new Date(event.timestamp) : null;
    const time = timestamp && !Number.isNaN(timestamp.getTime())
      ? `<time datetime="${esc(event.timestamp)}" title="${esc(timestamp.toLocaleString())}">${esc(timestamp.toLocaleTimeString())}</time>` : "";
    return `<li class="agent-route-step" data-status="${esc(event.status)}"><span class="agent-route-number">${String(index + 1).padStart(2, "0")}</span><div><strong>${esc(event.agent)}</strong><small>${esc(event.summary)}</small><span class="agent-route-state">${esc(event.status)} ${time}</span></div></li>`;
  }).join("") : '<li class="agent-route-waiting">Preparing the request. Waiting for an agent update…</li>';
}
function syncAgentWorkflow() {
  if (agentWorkflowRun?.status === "Running") return;
  agentWorkflowRun = null;
  renderAgentWorkflow();
}
function beginAgentWorkflow(kind) {
  agentWorkflowRun = {kind, status: "Running", agents: new Map()};
  renderAgentWorkflow();
}
function updateAgentWorkflow(event) {
  if (!agentWorkflowRun) return;
  const previous = agentWorkflowRun.agents.get(event.agent);
  const status = event.status === "info" && previous ? previous.status : event.status;
  agentWorkflowRun.agents.set(event.agent, {...event, status});
  renderAgentWorkflow();
}
function finishAgentWorkflow(status) {
  if (!runCompletionNotified) {
    const stage = generationStages[activeGeneration?.kind];
    addNotification(status === "Completed" ? `${stage?.label || "Generation"} completed` : `Operation ${status.toLowerCase()}`,
      status === "Completed" ? "The operation finished. Review its output and validation evidence in the workspace." : "The operation stopped. Review its status and recorded validation evidence.",
      status === "Completed" ? "success" : status === "Cancelled" ? "info" : "error");
    runCompletionNotified = true;
  }
  if (agentWorkflowRun) {
    agentWorkflowRun.status = status;
    agentWorkflowRun.agents.forEach((event, key) => {
      if (["running", "started", "pending"].includes(event.status))
        agentWorkflowRun.agents.set(key, { ...event, status: "finished", summary: `Last reported: ${event.summary}` });
    });
  }
  generationOperation.finish(status);
  updateGenerationBanner();
  generationFinishedAt = performance.now();
  renderGenerationOverview();
  paintValidationEvidence();
  updateGenerationClock();
  $("generation-background-state").textContent = status.toUpperCase();
  $("live-agent-feed-state").textContent = status.toUpperCase();
  $("generation-current-agent").textContent = `Operation ${status.toLowerCase()}`;
  $("generation-current-activity").textContent = status === "Completed"
    ? "Processing has finished. Review the output and recorded validation evidence."
    : "Processing has stopped. Review the operation result and recorded activity.";
  $("generation-agent-label").textContent = status;
  $("generation-overlay-title").textContent = `${generationStages[lastGenerationTarget]?.label || "Generation"} · ${status}`;
  $("generation-overlay-message").textContent = "Review the recorded agent progress and validation evidence for this operation.";
  $("cancel-generation-overlay").hidden = true;
  $("background-generation-label").textContent = "Back to progress";
  document.querySelector(".generation-agent-pulse").classList.add("hidden");
  $("generation-overlay").querySelector(".generation-progress").classList.add("hidden");
  if (generationOverlayTimer) clearInterval(generationOverlayTimer);
  generationOverlayTimer = null;
  if (!lifecycleSequence) {
    const empty = $("generation-background-events").querySelector(".empty-event");
    if (empty) empty.textContent =
      `Request ${status.toLowerCase()}. No backend agent activity was received; review the operation result or detailed logs.`;
    $("generation-current-agent").textContent = `Request ${status.toLowerCase()}`;
    $("generation-current-activity").textContent = "No backend activity was reported for this request.";
  }
  if (backgroundProgressUsed) showBackgroundProgress();
  renderAgentWorkflow();
}
window.addEventListener("workspace-role-ready", syncAgentWorkflow);
function selectedGenerationTarget() {
  return $("output-target").value === "non_functional" ? "manual" : $("output-target").value;
}
function syncManualTestingType() {
  const nonFunctional = $("output-target").value === "non_functional";
  const select = $("manual-testing-type");
  const choices = nonFunctional
    ? [
        ["performance", "Performance testing"],
        ["database", "Database testing"],
      ]
    : [
        ["api", "API testing"],
        ["ui", "UI testing"],
      ];
  const previous = select.value;
  select.replaceChildren(...choices.map(([value, label]) => new Option(label, value)));
  select.value = choices.some(([value]) => value === previous) ? previous : choices[0][0];
  $("manual-type-control").title = nonFunctional
    ? "Choose performance or database testing."
    : "Choose API or UI testing.";
  syncAgentWorkflow();
  if (typeof syncSuiteFileActions === "function") syncSuiteFileActions();
}
function automationControlsRestricted() {
  const target = $("output-target").value;
  return target === "non_functional";
}
$("output-target").addEventListener("change", syncManualTestingType);
$("manual-testing-type").addEventListener("change", syncManualTestingType);
async function loadAvailableModels() {
  const select = $("llm-model"),
    refresh = $("refresh-llm-models"),
    previous = select.value;
  ++modelAccessRequest;
  select.disabled = true;
  select.dataset.access = "checking";
  refresh.disabled = true;
  select.replaceChildren(new Option("Checking available models…", ""));
  $("llm-model-status").textContent = "Checking connected accounts and model permissions.";
  syncGenerateAvailability();
  try {
    const response = await fetch("/api/llm/models");
    if (!response.ok) throw await responseError(response);
    const result = await response.json();
    const models = result.models.filter((model) => model.can_use || model.visible_in_ui);
    select.replaceChildren(
      ...models.map((model) => {
        const option = new Option(model.display_name, model.model);
        option.title = model.reason;
        return option;
      }),
    );
    if (models.length) {
      if (models.some((model) => model.model === previous)) select.value = previous;
      select.disabled = false;
      const selected = models.find((model) => model.model === select.value);
      select.dataset.access = selected.can_use ? "allowed" : "blocked";
      $("llm-model-status").textContent = selected.can_use
        ? "Models that pass account access checks can generate. Usage limits can change."
        : selected.reason;
      syncSelectedRuntimeDetails();
    } else {
      select.replaceChildren(new Option("No models available", ""));
      select.dataset.access = "blocked";
      $("llm-model-status").textContent =
        "No connected model passed the access check. Check your account access or quota, then refresh.";
    }
  } catch (error) {
    select.replaceChildren(new Option("Models unavailable", ""));
    select.dataset.access = "blocked";
    $("llm-model-status").textContent = "Unable to check model availability. Refresh to try again.";
  } finally {
    refresh.disabled = false;
    syncGenerateAvailability();
  }
}
$("refresh-llm-models").addEventListener("click", loadAvailableModels);
if (document.body.dataset.guest !== "true") loadAvailableModels();
$("llm-model").addEventListener("change", () => {
  syncSelectedRuntimeDetails();
  checkModelAccess();
});
const descriptionInput = $("description"),
  characterCount = $("character-count");
descriptionInput.addEventListener("input", () => {
  const count = descriptionInput.value.length;
  characterCount.textContent = `${count} character${count === 1 ? "" : "s"}`;
  syncGenerateAvailability();
});
syncGenerateAvailability();
syncManualTestingType();
setWorkflowStage(1);
loadRuntimeStatus();

async function loadUserProfile() {
  try {
    window.renderWorkspaceProfile(await window.loadWorkspaceProfile());
  } catch {
    $("profile-name").textContent = "Profile unavailable";
  }
}
loadUserProfile();
