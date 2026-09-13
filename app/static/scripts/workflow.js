/* Five explicit handoffs. Drafts stay in this workspace while navigating its pages. */
(() => {
  const state = {
    request: null,
    stories: null,
    scenarios: null,
    storiesReviewed: false,
    scenariosReviewed: false,
    busy: false,
    plan: null,
    runReport: null,
    stage: 1,
  };
  const tabs = [...document.querySelectorAll("[data-stage]")];
  $("stage-panel-1").append(document.querySelector(".studio-layout"));
  $("stage-generation-options").classList.add("generation-options");
  $("stage-generation-options").append(
    $("output-target").closest("fieldset"),
    $("manual-type-control"),
  );
  $("stage-panel-4").insertBefore($("results"), $("review-cases"));
  const status = (message) => {
    $("stage-status").textContent = message;
  };
  function show(stage, focus = true) {
    state.stage = stage;
    tabs.forEach((tab, index) => {
      const active = index + 1 === stage;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      $(`stage-panel-${index + 1}`).hidden = !active;
      if (active && focus) tab.focus();
    });
    $("stage-position").textContent = `Stage ${stage} of 5`;
  }
  tabs.forEach((tab, index) => {
    tab.onclick = () => show(index + 1, false);
    tab.onkeydown = (event) => {
      const next = { ArrowRight: (index + 1) % 5, ArrowLeft: (index + 4) % 5, Home: 0, End: 4 }[
        event.key
      ];
      if (next !== undefined) {
        event.preventDefault();
        show(next + 1);
      }
    };
  });
  function sync() {
    $("stage-stories").disabled = state.busy || !state.request;
    $("review-stories").disabled = state.busy || !state.stories;
    $("stage-scenarios").disabled = state.busy || !state.storiesReviewed;
    $("review-scenarios").disabled = state.busy || !state.scenarios;
    $("stage-cases").disabled = state.busy || !state.scenariosReviewed;
    $("review-cases").disabled = state.busy || !suite;
    $("stage-refresh-execution").disabled = state.busy || !suite;
    $("stage-run").disabled = state.busy || !state.plan?.ready;
    $("save-stories").disabled = state.busy;
    $("save-scenarios").disabled = state.busy;
    tabs.forEach((tab, i) =>
      tab.classList.toggle(
        "complete",
        Boolean(
          [
            state.request,
            state.storiesReviewed,
            state.scenariosReviewed,
            suite,
            executionSummary || state.runReport,
          ][i],
        ),
      ),
    );
  }
  function invalidate(from) {
    if (from <= 1) state.request = null;
    if (from <= 2) {
      state.stories = null;
      state.storiesReviewed = false;
      $("story-cards").innerHTML =
        '<p class="stage-empty">Create stories from the current requirements.</p>';
      $("story-edit").hidden = true;
    }
    if (from <= 3) {
      state.scenarios = null;
      state.scenariosReviewed = false;
      $("scenario-cards").innerHTML =
        '<p class="stage-empty">Review stories before creating scenarios.</p>';
      $("scenario-edit").hidden = true;
    }
    suite = null;
    validationReport = null;
    reviewSourceRequest = null;
    executionSummary = null;
    resetSuiteFiles();
    $("results").classList.add("hidden");
    $("stage-case-empty").hidden = false;
    state.plan = null;
    state.runReport = null;
    $("stage-manual").replaceChildren();
    $("stage-execution-list").replaceChildren();
    $("stage-execution-results").replaceChildren();
    $("stage-execution-reason").textContent = "Create test cases in stage 4 first.";
    sync();
  }
  let revision = 0;
  function sourceChanged() {
    revision += 1;
    if (!state.request) return;
    invalidate(1);
    status("Requirements changed. Read them again to refresh downstream stages.");
  }
  ["description", "business-rules", "requirement-file", "business-rules-file"].forEach((id) =>
    $(id).addEventListener("input", sourceChanged),
  );
  ["file-remove", "rule-file-remove", "load-jira", "clear-business-rules"].forEach((id) =>
    $(id).addEventListener("click", sourceChanged),
  );
  window.addEventListener("workspace-source-replaced", sourceChanged);
  ["output-target", "manual-testing-type", "llm-model"].forEach((id) =>
    $(id).addEventListener("change", () => {
      revision += 1;
      invalidate(4);
    }),
  );
  async function work(message, task) {
    if (state.busy) return;
    state.busy = true;
    sync();
    status(message);
    const version = revision;
    const current = () => {
      if (version !== revision)
        throw new Error(
          "Inputs changed during this operation. Retry using the current requirements.",
        );
    };
    try {
      await task(current);
    } catch (error) {
      status(error.message);
    } finally {
      state.busy = false;
      sync();
    }
  }
  const post = async (path, body) => (await api(`/api/workflow/${path}`, body)).json();
  function requestOptions() {
    const target = $("output-target").value;
    return {
      ...state.request,
      generation_target: target,
      output_format: target === "manual" ? "normal" : "bdd",
      manual_testing_type: $("manual-testing-type").value,
      llm_model: $("llm-model").value || "auto-fallback",
    };
  }
  $("generate-form").addEventListener(
    "submit",
    (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      work("Reading source requirements…", async (current) => {
        let description = $("description").value.trim();
        const selected = attachedFile;
        if (selected) {
          const form = new FormData();
          form.append("file", selected);
          const result = await (await upload("/api/workflow/requirements/document", form)).json();
          current();
          description = [description, result.description].filter(Boolean).join("\n\n");
        }
        if (description.length < 10)
          throw new Error("Enter at least 10 characters or attach a readable BRD.");
        if (description.length > 30000)
          throw new Error("Split the requirements into batches of at most 30,000 characters.");
        await resolveBusinessRules();
        current();
        invalidate(2);
        state.request = {
          description,
          business_rules: parseBusinessRules(),
          additional_context: "",
        };
        $("description").value = description;
        if (selected) clearFile();
        status("Requirements read. Review the source in stage 1, then create stories in stage 2.");
        show(2);
      });
    },
    true,
  );
  const questions = (items) =>
    items?.length
      ? `<div class="stage-card"><h3>Open questions</h3><ul>${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></div>`
      : "";
  function editField(name, label, value) {
    return `<label class="stage-edit-field">${esc(label)}<textarea data-field="${name}">${esc(value)}</textarea></label>`;
  }
  function editedItems(selector, originals) {
    return [...document.querySelectorAll(selector)].map((card, index) => {
      const item = { ...originals[index] };
      card.querySelectorAll("[data-field]").forEach((field) => {
        item[field.dataset.field] = Array.isArray(item[field.dataset.field])
          ? field.value
              .split("\n")
              .map((line) => line.trim())
              .filter(Boolean)
          : field.value.trim();
      });
      return item;
    });
  }
  function renderStories() {
    $("story-cards").innerHTML =
      state.stories.stories
        .map(
          (story) =>
            `<article class="stage-card"><span class="chip">${esc(story.id)}</span><h3>${esc(story.title)}</h3><p>${esc(story.narrative)}</p><blockquote>${esc(story.source_excerpt)}</blockquote><strong>Acceptance criteria</strong><ul>${story.acceptance_criteria.map((ac) => `<li>${esc(ac)}</li>`).join("")}</ul></article>`,
        )
        .join("") + questions(state.stories.open_questions);
    $("story-editor").innerHTML = state.stories.stories
      .map(
        (story, index) =>
          `<div class="stage-card" data-story-index="${index}"><h3>${esc(story.id)}</h3>${editField("title", "Title", story.title)}${editField("narrative", "Story", story.narrative)}${editField("source_excerpt", "Source excerpt (exact words from requirements)", story.source_excerpt)}${editField("acceptance_criteria", "Acceptance criteria (one per line)", story.acceptance_criteria.join("\n"))}</div>`,
      )
      .join("");
    $("story-edit").hidden = false;
  }
  function renderScenarios() {
    $("scenario-cards").innerHTML =
      state.scenarios.scenarios
        .map(
          (scenario) =>
            `<article class="stage-card"><span class="chip">${esc(scenario.id)} → ${esc(scenario.story_id)}</span><h3>${esc(scenario.title)}</h3><p><strong>Preconditions:</strong> ${esc(scenario.preconditions.join("; ") || "None specified")}</p><p><strong>Action:</strong> ${esc(scenario.action)}</p><p><strong>Expected:</strong> ${esc(scenario.expected_result)}</p><ul>${scenario.acceptance_criteria.map((ac) => `<li>${esc(ac)}</li>`).join("")}</ul></article>`,
        )
        .join("") + questions(state.scenarios.open_questions);
    $("scenario-editor").innerHTML = state.scenarios.scenarios
      .map(
        (scenario, index) =>
          `<div class="stage-card" data-scenario-index="${index}"><h3>${esc(scenario.id)} → ${esc(scenario.story_id)}</h3>${editField("title", "Title", scenario.title)}${editField("preconditions", "Preconditions (one per line)", scenario.preconditions.join("\n"))}${editField("action", "Action", scenario.action)}${editField("expected_result", "Expected result", scenario.expected_result)}${editField("acceptance_criteria", "Covered story acceptance criteria (one per line)", scenario.acceptance_criteria.join("\n"))}</div>`,
      )
      .join("");
    $("scenario-edit").hidden = false;
  }
  $("stage-stories").onclick = () =>
    work("Story Agent is converting requirements into stories…", async (current) => {
      const result = await post("stories", requestOptions());
      current();
      invalidate(2);
      state.stories = result;
      renderStories();
      status("Stories ready. Review or edit them, then choose “Use these stories”.");
    });
  $("review-stories").onclick = () => {
    state.storiesReviewed = true;
    sync();
    show(3);
    status("Stories reviewed. Create scenario coverage for these requirements.");
  };
  $("stage-scenarios").onclick = () =>
    work("Scenario Agent is designing story coverage…", async (current) => {
      const result = await post("scenarios", { request: requestOptions(), stories: state.stories });
      current();
      invalidate(3);
      state.scenarios = result;
      renderScenarios();
      status("Scenarios ready. Review or edit them before creating test cases.");
    });
  $("review-scenarios").onclick = () => {
    state.scenariosReviewed = true;
    sync();
    show(4);
    status("Scenarios reviewed. Choose a test format and create test cases.");
  };
  $("save-stories").onclick = () =>
    work("Validating story edits…", async (current) => {
      const result = {
        ...state.stories,
        stories: editedItems("[data-story-index]", state.stories.stories),
      };
      await post("validate-stories", { request: requestOptions(), stories: result });
      current();
      invalidate(2);
      state.stories = result;
      renderStories();
      status("Story edits applied. Review the updated stories to continue.");
    });
  $("save-scenarios").onclick = () =>
    work("Validating scenario edits…", async (current) => {
      const result = {
        ...state.scenarios,
        scenarios: editedItems("[data-scenario-index]", state.scenarios.scenarios),
      };
      await post("validate-scenarios", {
        request: requestOptions(),
        stories: state.stories,
        scenarios: result,
      });
      current();
      invalidate(3);
      state.scenarios = result;
      renderScenarios();
      status("Scenario edits applied. Review the updated scenarios to continue.");
    });
  $("stage-cases").onclick = () =>
    work("Test Case Agent is generating and validating cases…", async (current) => {
      const result = await post("test-cases", {
        request: requestOptions(),
        stories: state.stories,
        scenarios: state.scenarios,
      });
      current();
      invalidate(4);
      validationReport = result.validation;
      reviewSourceRequest = result.source_request;
      render(result.suite);
      $("stage-case-empty").hidden = true;
      status(
        `Created ${suite.test_cases.length} cases. Quality Gate: ${validationReport.passed ? "passed" : "needs review"}.`,
      );
    });
  function manualMarkup() {
    const manual = suite.test_cases.filter((item) => item.execution_mode === "manual");
    if (!manual.length) {
      $("stage-manual").replaceChildren();
      return;
    }
    const previous = new Map(
      (executionSummary?.results || []).map((result) => [result.case_id, result]),
    );
    $("stage-manual").innerHTML =
      "<h3>Manual execution</h3><p>Follow each case’s steps in stage 4, then record the observed result here.</p>" +
      manual
        .map(
          (item) =>
            `<div class="stage-manual-row" data-case-id="${esc(item.id)}"><strong>${esc(item.id)} · ${esc(item.title)}</strong><select aria-label="Outcome for ${esc(item.id)}">${["not-run", "passed", "failed", "blocked"].map((value) => `<option value="${value}" ${previous.get(item.id)?.status === value ? "selected" : ""}>${value}</option>`).join("")}</select><textarea aria-label="Actual result for ${esc(item.id)}" placeholder="Actual result and evidence reference">${esc(previous.get(item.id)?.actual_result || "")}</textarea></div>`,
        )
        .join("") +
      '<button type="button" class="secondary" id="save-stage-manual">Save manual results</button>';
    $("save-stage-manual").onclick = () =>
      work("Recording manual execution…", async (current) => {
        const results = [...document.querySelectorAll(".stage-manual-row")].map((row) => ({
          case_id: row.dataset.caseId,
          status: row.querySelector("select").value,
          actual_result: row.querySelector("textarea").value,
        }));
        if (results.some((item) => item.status !== "not-run" && !item.actual_result.trim()))
          throw new Error("Add an actual result for each executed or blocked manual case.");
        const result = await (await api("/api/execution", { suite, results })).json();
        current();
        executionSummary = result;
        status(
          `Manual results saved: ${result.passed} passed, ${result.failed} failed, ${result.blocked} blocked.`,
        );
      });
  }
  function renderPlan(running = false) {
    $("stage-execution-list").innerHTML = (state.plan?.cases || [])
      .map(
        (item) =>
          `<article class="stage-card"><span class="chip">${esc(item.feature_file)}</span><h3>${esc(item.scenario)}</h3><p>${running ? "Submitted to runner · individual progress unavailable until results return" : esc(state.plan?.runStatus || (state.plan?.ready ? "Listed in configured project · not run" : "Not run · target configuration required"))}</p></article>`,
      )
      .join("");
  }
  async function refreshExecution(current) {
    manualMarkup();
    if (!suite.test_cases.some((item) => item.execution_mode === "automation")) {
      state.plan = null;
      state.runReport = null;
      $("stage-execution-list").replaceChildren();
      $("stage-execution-reason").textContent = "This suite contains manual cases only.";
      return;
    }
    const result = await post("execution-plan", { suite, request: reviewSourceRequest });
    current();
    state.plan = result;
    $("stage-execution-reason").textContent = result.reason;
    renderPlan();
    status(
      result.ready
        ? "Execution plan ready. Review the feature list before running."
        : result.reason,
    );
  }
  $("review-cases").onclick = () => {
    show(5);
    work("Loading feature execution plan…", refreshExecution);
  };
  $("stage-refresh-execution").onclick = () =>
    work("Refreshing feature execution plan…", refreshExecution);
  $("stage-run").onclick = () =>
    work("ReqnRoll run in progress. Waiting for actual case results…", async (current) => {
      renderPlan(true);
      $("stage-execution-results").replaceChildren();
      try {
        const report = await post("execute", { suite, request: reviewSourceRequest });
        current();
        $("stage-execution-results").innerHTML =
          `<h3>Run ${esc(report.status)}</h3><p>${report.passed} passed · ${report.failed} failed · ${report.skipped} skipped</p>` +
          (report.test_results || [])
            .map(
              (item) =>
                `<div class="stage-result"><span>${esc(item.name)}</span><strong>${esc(item.status)}</strong></div>`,
            )
            .join("") +
          (report.error ? `<p>${esc(report.error)}</p>` : "");
        state.runReport = report;
        $("stage-execution-results").insertAdjacentHTML(
          "beforeend",
          `<details><summary>Runner output</summary><pre class="stage-run-output">${esc(report.output || "No additional output")}</pre></details>`,
        );
        state.plan.runStatus = `Run ${report.status} · see runner-reported case results below`;
        status(
          `ReqnRoll run ${report.status}. Results below are reported by the configured project.`,
        );
      } finally {
        renderPlan();
      }
    });
  window.addEventListener("workspace-suite-rendered", () => {
    state.plan = null;
    state.runReport = null;
    $("stage-execution-results").replaceChildren();
    $("stage-execution-list").replaceChildren();
    $("stage-manual").replaceChildren();
    $("stage-execution-reason").textContent = "Refresh the execution plan for the current suite.";
    $("stage-case-empty").hidden = true;
    show(4, false);
    sync();
  });
  show(1, false);
  sync();
})();
