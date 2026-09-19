/* View and download approved suite artifacts without regenerating cached C# files. */
let featureFile = null;
let stepDefinitionTask = null;
let stepDefinitionTimer = null;
let stepDefinitionRequest = null;
let packFileProgressTimer = null;
let packFileProgressSequence = 0;
let packFileProgressRequest = null;
const packGeneratedFiles = new Set();
const stepDefinitionCache = new Map();
function selectedLanguage() {
  return $("automation-language").value;
}
async function artifactPolicyKey() {
  const response = await fetch("/api/workspace/standards");
  if (!response.ok) throw await responseError(response);
  return JSON.stringify(await response.json());
}
$("automation-language").addEventListener("change", () => {
  resetSuiteFiles();
  syncSuiteFileActions();
});

function closeStepDefinitionProgress() {
  clearInterval(stepDefinitionTimer);
  stepDefinitionTimer = null;
  $("cs-generation-dialog").close();
}

function showStepDefinitionProgress() {
  if (!$("cs-generation-dialog").open) $("cs-generation-dialog").showModal();
}

function resetPackFileProgress() {
  if (packFileProgressTimer) clearTimeout(packFileProgressTimer);
  packFileProgressTimer = null;
  packFileProgressRequest = null;
  packFileProgressSequence = 0;
  packGeneratedFiles.clear();
  $("cs-generation-current-file").textContent = "Preparing files…";
  $("cs-generation-completed-files").innerHTML =
    '<li class="empty-file-progress">No files generated yet.</li>';
}

function updatePackFileProgress(events) {
  events.forEach((event) => {
    packFileProgressSequence = Math.max(packFileProgressSequence, event.sequence);
    if (event.action === "pack_stage" || event.action === "pack_generation") {
      $("cs-generation-current-file").textContent = event.summary;
      return;
    }
    if (event.action !== "file_generated" || event.status !== "success") return;
    const path = event.summary.replace(/^(?:Generating|Generated) file:\s*/, "");
    if (!path) return;
    packGeneratedFiles.add(path);
    $("cs-generation-completed-files").replaceChildren(
      ...Array.from(packGeneratedFiles, (file) => {
        const item = document.createElement("li");
        item.textContent = file;
        return item;
      }),
    );
  });
}

async function pollPackFileProgress(requestId) {
  if (packFileProgressRequest !== requestId) return;
  packFileProgressTimer = null;
  let complete = false;
  try {
    const response = await fetch(
      `/api/generation/${encodeURIComponent(requestId)}/events?after=${packFileProgressSequence}`,
      { signal: AbortSignal.timeout(10000) },
    );
    if (response.ok) {
      const data = await response.json();
      if (packFileProgressRequest !== requestId) return;
      updatePackFileProgress(data.events || []);
      complete = data.complete;
    }
  } catch {}
  if (packFileProgressRequest === requestId && !complete) {
    packFileProgressTimer = setTimeout(() => pollPackFileProgress(requestId), 250);
  }
}

function startPackFileProgress(requestId) {
  resetPackFileProgress();
  packFileProgressRequest = requestId;
  pollPackFileProgress(requestId);
}

function startStepDefinitionProgress() {
  $("cs-generation-title").textContent = "Generating automation pack";
  $("cs-generation-message").textContent =
    "Creating bindings, implementations and supporting files. Your pack will open when ready.";
  $("cs-generation-dialog").querySelector('[role="progressbar"]').classList.remove("hidden");
  $("hide-cs-generation").querySelector(".generation-action-label").textContent =
    "Run in background";
  $("cancel-cs-generation").classList.remove("hidden");
  $("cancel-cs-generation").disabled = false;
  $("cancel-cs-generation").querySelector(".generation-action-label").textContent =
    "Cancel generation";
  const started = Date.now();
  const update = () => {
    const seconds = Math.floor((Date.now() - started) / 1000);
    $("cs-generation-time").textContent =
      `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")} elapsed`;
  };
  update();
  stepDefinitionTimer = setInterval(update, 1000);
  showStepDefinitionProgress();
}

function closeSuiteMenus() {
  document.querySelectorAll(".suite-menu, .suite-jira").forEach((menu) => {
    menu.open = false;
  });
}

function resetSuiteFiles() {
  window.resetScriptPack?.();
  closeStepDefinitionProgress();
  resetPackFileProgress();
  featureFile = null;
  stepDefinitionArtifact = null;
  stepDefinitionTask = null;
  $("automation-language").disabled = false;
  $("feature-file-content").textContent = "";
  $("step-definition-files").replaceChildren();
  $("feature-file-view").classList.add("hidden");
  $("step-definitions").classList.add("hidden");
  $("cs-download-dialog").close();
  closeSuiteMenus();
}

function syncSuiteFileActions() {
  const approved = Boolean(suite?.test_cases.length && validationReport?.passed);
  $("open-script-pack").disabled = !approved;
  const containsAutomation = Boolean(
    suite?.test_cases.some((c) => c.execution_mode === "automation"),
  );
  const automation =
    approved && suite.test_cases.some((c) => c.execution_mode === "automation" && c.gherkin) &&
    !automationControlsRestricted();
  [
    "view-feature",
    "download-feature",
    "generate-step-definitions",
    "suite-download-cs",
    "view-csharp-pack",
    "download-csharp-pack",
  ].forEach((id) => {
    $(id).disabled = !automation;
    $(id).title = automation ? "" : "Requires a validated suite with BDD automation scenarios.";
  });
  const restricted = automationControlsRestricted();
  document.querySelectorAll("[data-automation-control]").forEach((control) => {
    if (control.matches("summary")) {
      control.setAttribute("aria-disabled", String(restricted));
      control.tabIndex = restricted ? -1 : 0;
      control.classList.toggle("is-disabled", restricted);
      if (restricted) control.parentElement.open = false;
    } else {
      if (restricted) control.disabled = true;
      if (!restricted && control.id === "automation-language") control.disabled = false;
      control.title = restricted
        ? "Unavailable for Performance or Database test cases."
        : control.title;
    }
  });
  ["xlsx", "csv", "pdf", "json"].forEach((id) => {
    $(id).disabled = !approved || containsAutomation;
    $(id).title = containsAutomation ? "Available only for manual test suites." : "";
  });
}

function requireApprovedSuite() {
  if (!suite || !validationReport?.passed) throw new Error("Generate and validate a suite first.");
}

function artifactFilename(response, fallback) {
  return response.headers.get("Content-Disposition")?.match(/filename="([^"]+)"/)?.[1] || fallback;
}

async function convert(format) {
  requireApprovedSuite();
  if (format !== "feature" && suite.test_cases.some((c) => c.execution_mode === "automation")) {
    throw new Error("Automation tests must be downloaded as .feature or .cs files.");
  }
  const snapshot = suite;
  const response = await api(`/api/context-converter/${format}`, {
    suite: snapshot,
    validation: validationReport,
  });
  const blob = await response.blob();
  if (suite !== snapshot) throw new Error("The suite changed. Download the current suite again.");
  download(blob, artifactFilename(response, `test-suite.${format}`));
}

async function viewFeatureFile() {
  requireApprovedSuite();
  const snapshot = suite;
  if (!featureFile) {
    const response = await api("/api/context-converter/feature", {
      suite: snapshot,
      validation: validationReport,
    });
    const content = await response.text();
    if (suite !== snapshot)
      throw new Error("The suite changed. Open the current feature file again.");
    featureFile = { content, name: artifactFilename(response, "automation-tests.feature") };
  }
  $("feature-file-name").textContent = featureFile.name;
  $("feature-file-content").textContent = featureFile.content;
  $("step-definitions").classList.add("hidden");
  $("feature-file-view").classList.remove("hidden");
  $("feature-file-view").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function ensureStepDefinitions() {
  requireApprovedSuite();
  const snapshot = suite;
  const validation = validationReport;
  const language = selectedLanguage();
  const cacheKey = "full-pack:" + language + (await artifactPolicyKey()) + JSON.stringify(snapshot);
  if (suite !== snapshot || selectedLanguage() !== language)
    throw new Error("Suite or language changed. Try again.");
  if (stepDefinitionCache.has(cacheKey)) {
    stepDefinitionArtifact = stepDefinitionCache.get(cacheKey);
    return stepDefinitionArtifact;
  }
  if (stepDefinitionTask) {
    showStepDefinitionProgress();
    return stepDefinitionTask;
  }
  const generation = {
    requestId: crypto.randomUUID(),
    controller: new AbortController(),
    cancelled: false,
  };
  stepDefinitionRequest = generation;
  $("status").textContent = "Generating automation pack…";
  $("automation-language").disabled = true;
  startStepDefinitionProgress();
  startPackFileProgress(generation.requestId);
  const task = (async () => {
    const response = await api(
      "/api/step-definitions/languages/pack",
      { suite: snapshot, validation, language },
      {
        requestId: generation.requestId,
        signal: generation.controller.signal,
      },
    );
    const artifact = await response.json();
    if (generation.cancelled) throw new DOMException("Generation cancelled", "AbortError");
    if (suite !== snapshot || selectedLanguage() !== language)
      throw new Error("The suite or language changed. Generate code for the current suite again.");
    stepDefinitionArtifact = artifact;
    stepDefinitionCache.set(cacheKey, artifact);
    if (stepDefinitionCache.size > 5) {
      stepDefinitionCache.delete(stepDefinitionCache.keys().next().value);
    }
    $("status").textContent = "Automation pack is ready to view or download.";
    return artifact;
  })();
  stepDefinitionTask = task;
  let failed = false;
  try {
    return await task;
  } catch (error) {
    if (generation.cancelled) {
      throw new DOMException("Automation pack generation cancelled.", "AbortError");
    }
    failed = true;
    if (stepDefinitionTask === task) {
      $("cs-generation-current-file").textContent = "Pack generation failed";
      $("cs-generation-title").textContent = "Automation generation could not complete";
      $("cs-generation-message").textContent = error.message;
      $("cs-generation-dialog").querySelector('[role="progressbar"]').classList.add("hidden");
      $("hide-cs-generation").querySelector(".generation-action-label").textContent = "Close";
      $("cancel-cs-generation").classList.add("hidden");
      showStepDefinitionProgress();
    }
    throw error;
  } finally {
    if (stepDefinitionTask === task) {
      $("automation-language").disabled = false;
      stepDefinitionTask = null;
      stepDefinitionRequest = null;
      clearInterval(stepDefinitionTimer);
      stepDefinitionTimer = null;
      packFileProgressRequest = null;
      if (packFileProgressTimer) clearTimeout(packFileProgressTimer);
      packFileProgressTimer = null;
      if (!failed) closeStepDefinitionProgress();
    }
  }
}

async function cancelFullPackGeneration() {
  const generation = stepDefinitionRequest;
  if (!generation || generation.cancelled) return;
  generation.cancelled = true;
  $("cancel-cs-generation").disabled = true;
  $("cancel-cs-generation").querySelector(".generation-action-label").textContent =
    "Cancelling…";
  try {
    const response = await fetch(
      `/api/generation/${encodeURIComponent(generation.requestId)}/cancel`,
      {
        method: "POST",
        signal: AbortSignal.timeout(10000),
      },
    );
    if (!response.ok) throw await responseError(response);
    const result = await response.json();
    if (!result.cancelled && stepDefinitionRequest === generation) {
      throw new Error("Generation could not be stopped yet. Please try Cancel again.");
    }
    generation.controller.abort();
  } catch (error) {
    if (stepDefinitionRequest !== generation) return;
    generation.cancelled = false;
    $("cancel-cs-generation").disabled = false;
    $("cancel-cs-generation").querySelector(".generation-action-label").textContent =
      "Cancel generation";
    $("cs-generation-message").textContent = error.message;
  }
}

async function viewStepDefinitions() {
  const artifact = await ensureBindingsOnly();
  $("feature-file-view").classList.add("hidden");
  renderStepDefinitions(artifact);
}

async function ensureBindingsOnly() {
  requireApprovedSuite();
  const snapshot = suite;
  const language = selectedLanguage();
  const key = "bindings:" + language + (await artifactPolicyKey()) + JSON.stringify(snapshot);
  if (!stepDefinitionCache.has(key)) {
    const response = await api("/api/step-definitions/languages/bindings", {
      suite: snapshot,
      validation: validationReport,
      language,
    });
    const artifact = await response.json();
    if (suite !== snapshot || selectedLanguage() !== language)
      throw new Error(
        "The suite or language changed. Generate step definitions for the current suite.",
      );
    stepDefinitionCache.set(key, artifact);
    if (stepDefinitionCache.size > 5)
      stepDefinitionCache.delete(stepDefinitionCache.keys().next().value);
  }
  stepDefinitionArtifact = stepDefinitionCache.get(key);
  $("status").textContent =
    "Step definitions are ready. Automation pack generation is a separate option.";
  return stepDefinitionArtifact;
}

async function downloadFullPack() {
  const artifact = await ensureStepDefinitions();
  const response = await api("/api/step-definitions/languages/download", artifact);
  download(await response.blob(), `automation-${artifact.language}.zip`);
}

function downloadCSharpFile(index) {
  const file = stepDefinitionArtifact?.files[index];
  if (file)
    download(
      new Blob([file.content], { type: "text/plain;charset=utf-8" }),
      file.path.split("/").pop(),
    );
}

async function chooseCSharpDownload() {
  const artifact = await ensureStepDefinitions();
  if (artifact.files.length === 1) {
    downloadCSharpFile(0);
    return;
  }
  $("cs-download-files").replaceChildren(
    ...artifact.files.map((file, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = `↓ ${file.path}`;
      button.onclick = () => downloadCSharpFile(index);
      return button;
    }),
  );
  if (!$("cs-download-dialog").open) $("cs-download-dialog").showModal();
}

function suiteFileAction(action) {
  return async () => {
    closeSuiteMenus();
    try {
      await action();
    } catch (error) {
      $("status").textContent = error.message;
    }
  };
}

["xlsx", "csv", "pdf", "json"].forEach((format) => {
  $(format).onclick = suiteFileAction(() => convert(format));
});
$("download-feature").onclick = suiteFileAction(() => convert("feature"));
$("view-feature").onclick = suiteFileAction(viewFeatureFile);
$("generate-step-definitions").onclick = suiteFileAction(viewStepDefinitions);
$("suite-download-cs").onclick = suiteFileAction(async () => {
  const artifact = await ensureBindingsOnly();
  const file = artifact.files[0];
  download(
    new Blob([file.content], { type: "text/plain;charset=utf-8" }),
    file.path.split("/").pop(),
  );
});
$("view-csharp-pack").onclick = suiteFileAction(async () => {
  const artifact = await ensureStepDefinitions();
  $("feature-file-view").classList.add("hidden");
  renderStepDefinitions(artifact);
});
$("download-csharp-pack").onclick = suiteFileAction(downloadFullPack);
$("copy-feature-file").onclick = () =>
  featureFile && copyText(featureFile.content, featureFile.name);
$("close-feature-view").onclick = () => $("feature-file-view").classList.add("hidden");
$("close-step-view").onclick = () => $("step-definitions").classList.add("hidden");
$("close-cs-download").onclick = () => $("cs-download-dialog").close();
$("hide-cs-generation").onclick = () => $("cs-generation-dialog").close();
$("cancel-cs-generation").onclick = cancelFullPackGeneration;
$("download-step-definitions").onclick = suiteFileAction(async () => {
  const artifact = await ensureStepDefinitions();
  const response = await api("/api/step-definitions/languages/download", artifact);
  download(await response.blob(), `automation-${artifact.language}.zip`);
});
$("step-definition-files").addEventListener("click", (event) => {
  const button = event.target.closest(".copy-step-definition");
  if (button && stepDefinitionArtifact) {
    const file = stepDefinitionArtifact.files[Number(button.dataset.index)];
    copyText(file.content, file.path);
  }
});
document.addEventListener("click", (event) => {
  document.querySelectorAll(".suite-menu, .suite-jira").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    const menu = document.querySelector(".suite-menu[open], .suite-jira[open]");
    if (menu) {
      closeSuiteMenus();
      menu.querySelector("summary").focus();
    }
  }
});
syncSuiteFileActions();
