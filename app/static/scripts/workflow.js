/* Five explicit handoffs. Drafts stay in this workspace while navigating its pages. */
(() => {
  const state = {
    request: null,
    stories: null,
    scenarios: null,
    storiesReviewed: false,
    acceptedStories: new Map(),
    jiraStories: new Map(),
    dirtyStories: new Set(),
    scenariosReviewed: false,
    acceptedScenarios: new Map(),
    dirtyScenarios: new Set(),
    busy: false,
    plan: null,
    runReport: null,
    stage: 1,
  };
  const tabs = [...document.querySelectorAll("[data-stage]")];
  const workspace = document.querySelector(".stage-workspace");
  workspace.before(document.querySelector(".studio-layout"));
  $("stage-panel-4").insertBefore($("results"), $("review-cases"));
  const status = (message) => {
    $("stage-status").textContent = message;
    $("status").textContent = message;
  };
  function show(stage, focus = true) {
    state.stage = stage;
    workspace.hidden = !state.stories && !suite;
    tabs.forEach((tab, index) => {
      const active = index + 1 === stage;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      $(`stage-panel-${index + 1}`).hidden = !active;
      if (active && focus) tab.focus();
    });
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
    workspace.hidden = !state.stories && !suite;
    syncGenerateAvailability();
    $("generate").disabled ||= state.busy;
    $("stage-stories").disabled = state.busy || !state.request || allStoriesAccepted();
    $("stage-stories").title = allStoriesAccepted()
      ? "Stories are approved. Continue to scenarios, or change the requirements to create new stories."
      : "Create stories from the current requirements";
    $("review-stories").disabled = state.busy || !allStoriesAccepted();
    $("story-review-progress").textContent = state.stories
      ? `${state.acceptedStories.size} of ${state.stories.stories.length} stories accepted. Select stories and accept them together, or accept individually.`
      : "Select and accept stories to continue.";
    document.querySelectorAll("[data-story-index]").forEach((card) => {
      const story = state.stories.stories[Number(card.dataset.storyIndex)];
      const accepted = state.acceptedStories.has(story.id);
      const dirty = state.dirtyStories.has(story.id);
      card.querySelector(".story-check").disabled = state.busy || dirty;
      if (dirty) card.querySelector(".story-check").checked = false;
      card.querySelector(".story-accept").disabled = state.busy || accepted || dirty;
      card.querySelector(".story-accept").textContent = accepted ? "Accepted" : "Accept story";
      card.querySelector(".story-review-state").textContent = accepted
        ? "Accepted"
        : dirty
          ? "Unsaved edits"
          : "Review required";
      card
        .querySelectorAll("textarea, .story-save, .story-cancel-edit, .story-open-edit")
        .forEach((control) => (control.disabled = state.busy));
    });
    const available = [...document.querySelectorAll(".story-check:not(:disabled)")];
    const selected = available.filter((checkbox) => checkbox.checked);
    $("select-all-stories").disabled = state.busy || !available.length;
    $("select-all-stories").checked = available.length > 0 && selected.length === available.length;
    $("select-all-stories").indeterminate =
      selected.length > 0 && selected.length < available.length;
    $("story-selection-count").textContent = `${selected.length} selected`;
    $("accept-selected-stories").disabled =
      state.busy ||
      !selected.some(
        (checkbox) =>
          !state.acceptedStories.has(
            state.stories.stories[Number(checkbox.closest("[data-story-index]").dataset.storyIndex)]
              .id,
          ),
      );
    $("story-jira-open").disabled = state.busy || !selectedApprovedStories().length;
    $("stories-accepted-by").disabled = state.busy;
    $("stage-scenarios").disabled = state.busy || !state.storiesReviewed;
    $("review-scenarios").disabled = state.busy || !allScenariosAccepted();
    $("accept-scenarios").disabled = state.busy || !state.scenarios || allScenariosAccepted();
    $("scenarios-accepted-by").disabled = state.busy;
    $("scenario-cards")
      .querySelectorAll("[data-scenario-index]")
      .forEach((card) => {
        const scenario = state.scenarios.scenarios[Number(card.dataset.scenarioIndex)];
        card.querySelector(".scenario-review-state").textContent = state.dirtyScenarios.has(
          scenario.id,
        )
          ? "Unsaved edits"
          : state.acceptedScenarios.has(scenario.id)
            ? `Approved by ${state.acceptedScenarios.get(scenario.id)}`
            : "Review required";
        card.querySelector(".scenario-open-edit").disabled = state.busy;
      });
    $("stage-cases").disabled = state.busy || !state.scenariosReviewed;
    $("review-cases").disabled = state.busy || !suite;
    $("stage-refresh-execution").disabled = state.busy || !suite;
    $("stage-run").disabled = state.busy || !state.plan?.ready;
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
      state.acceptedStories.clear();
      state.jiraStories.clear();
      state.dirtyStories.clear();
      storyReviewerError(false);
    }
    if (from <= 3) {
      state.scenarios = null;
      state.scenariosReviewed = false;
      state.acceptedScenarios.clear();
      state.dirtyScenarios.clear();
      $("scenario-cards").innerHTML =
        '<p class="stage-empty">Review stories before creating scenarios.</p>';
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
    status("Requirements changed. Generate stories again to refresh downstream stages.");
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
  async function work(message, task, kind = null) {
    if (state.busy || activeGeneration) return;
    const operation = kind
      ? {
          requestId: crypto.randomUUID(),
          controller: new AbortController(),
          cancelled: false,
          background: false,
          kind,
          initiator: document.activeElement,
        }
      : null;
    if (operation) {
      activeGeneration = operation;
      operation.cancel = async () => {
        if (operation.cancelled) return;
        operation.cancelled = true;
        operation.controller.abort();
        hideGenerationOverlay();
        status(`${generationStages[kind].label} cancelled.`);
        if (kind === "execution" && state.plan) {
          state.plan.runStatus = "Run cancelled · partial results unavailable";
          renderPlan();
        }
        try {
          const response = await fetch(
            `/api/generation/${encodeURIComponent(operation.requestId)}/cancel`,
            { method: "POST" },
          );
          if (!response.ok) throw await responseError(response);
        } catch {
          addNotification(
            "Cancellation could not be confirmed",
            "The local request was stopped, but the server could not confirm cancellation.",
            "error",
          );
        }
      };
      $("stop-generation").classList.remove("hidden");
      startLifecycleFeed(operation.requestId);
      showGenerationOverlay(kind);
    }
    state.busy = true;
    sync();
    status(message);
    const version = revision;
    const current = () => {
      if (operation?.cancelled)
        throw new DOMException(`${generationStages[kind].label} cancelled.`, "AbortError");
      if (version !== revision)
        throw new Error(
          "Inputs changed during this operation. Retry using the current requirements.",
        );
    };
    try {
      await task(current);
    } catch (error) {
      status(operation?.cancelled ? `${generationStages[kind].label} cancelled.` : error.message);
    } finally {
      if (operation) {
        await stopLifecycleFeed(operation.requestId);
        activeGeneration = null;
        $("stop-generation").classList.add("hidden");
        hideGenerationOverlay();
      }
      state.busy = false;
      sync();
      if (operation && !operation.background) operation.initiator?.focus();
    }
  }
  const transportOptions = () =>
    activeGeneration?.kind
      ? { requestId: activeGeneration.requestId, signal: activeGeneration.controller.signal }
      : {};
  const post = async (path, body) =>
    (await api(`/api/workflow/${path}`, body, transportOptions())).json();
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
      work(
        "Reading source requirements…",
        async (current) => {
          let description = $("description").value.trim();
          const selected = attachedFile;
          if (selected) {
            const form = new FormData();
            form.append("file", selected);
            const result = await (
              await upload("/api/workflow/requirements/document", form, transportOptions())
            ).json();
            current();
            description = [description, result.description].filter(Boolean).join("\n\n");
          }
          if (description.length < 10)
            throw new Error("Enter at least 10 characters or attach a readable BRD.");
          if (description.length > 30000)
            throw new Error("Split the requirements into batches of at most 30,000 characters.");
          current();
          await resolveBusinessRules(transportOptions());
          current();
          invalidate(2);
          state.request = {
            description,
            business_rules: parseBusinessRules(),
            additional_context: "",
          };
          status("Story Agent is converting requirements into stories…");
          const result = await post("stories", requestOptions());
          current();
          state.stories = result;
          renderStories();
          status("Stories ready. Review, edit and accept each story to continue.");
          show(2, !activeGeneration?.background);
          if (!activeGeneration?.background)
            workspace.scrollIntoView({ behavior: "smooth", block: "start" });
        },
        "stories",
      );
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
  function allStoriesAccepted() {
    return (
      Boolean(state.stories?.stories.length) &&
      !state.dirtyStories.size &&
      state.stories.stories.every((story) => state.acceptedStories.has(story.id))
    );
  }
  function storyMarkup(story, index) {
    return `<article class="stage-card" data-story-index="${index}">
      <div class="story-review-heading"><label><input class="story-check" type="checkbox" checked aria-label="Select ${esc(story.id)} for acceptance" /> <span class="chip">${esc(story.id)}</span></label><span class="story-review-state">Review required</span></div>
      <h3>${esc(story.title)}</h3><p>${esc(story.narrative)}</p>
      <blockquote>${esc(story.source_excerpt)}</blockquote><strong>Acceptance criteria</strong>
      <ul>${story.acceptance_criteria.map((ac) => `<li>${esc(ac)}</li>`).join("")}</ul>
      <button class="secondary story-open-edit" type="button" aria-haspopup="dialog">Edit ${esc(story.id)}</button>
      <dialog class="story-edit story-edit-dialog" aria-labelledby="story-edit-title-${index}">
        <h2 id="story-edit-title-${index}">Edit ${esc(story.id)}</h2>
        <p>Update the story details, or discard to keep the current story.</p>
        ${editField("title", "Title", story.title)}
        ${editField("narrative", "Story", story.narrative)}
        ${editField("source_excerpt", "Source excerpt (exact words from requirements)", story.source_excerpt)}
        ${editField("acceptance_criteria", "Acceptance criteria (one per line)", story.acceptance_criteria.join("\n"))}
        <div class="story-review-actions"><button class="secondary story-save" type="button">Update</button>
        <button class="secondary story-cancel-edit" type="button">Discard</button></div>
        <p class="story-dialog-status" role="alert"></p>
      </dialog>
      <p class="story-edit-status" role="status"></p>
      <button class="primary story-accept" type="button" aria-label="Accept ${esc(story.id)}">Accept story</button>
    </article>`;
  }
  function renderStories() {
    $("story-cards").innerHTML =
      state.stories.stories.map(storyMarkup).join("") + questions(state.stories.open_questions);
  }
  function selectedApprovedStories() {
    return [...document.querySelectorAll(".story-check:checked:not(:disabled)")]
      .map(
        (checkbox) =>
          state.stories.stories[Number(checkbox.closest("[data-story-index]").dataset.storyIndex)],
      )
      .filter((story) => state.acceptedStories.has(story.id) && !state.jiraStories.has(story.id));
  }
  $("story-jira-open").onclick = () => {
    $("story-jira-selection").textContent =
      `${selectedApprovedStories().length} selected approved stories to create.`;
    $("story-jira-create").disabled = false;
    $("story-jira-dialog").showModal();
  };
  $("story-jira-close").onclick = () => $("story-jira-dialog").close();
  $("story-jira-dialog").addEventListener("cancel", (event) => {
    if (state.busy) event.preventDefault();
  });
  $("story-jira-create").onclick = async () => {
    const selected = selectedApprovedStories();
    const project = $("story-jira-project").value.trim().toUpperCase();
    const issueType = $("story-jira-type").value.trim();
    if (!selected.length || !/^[A-Z][A-Z0-9_]*$/.test(project) || !issueType) {
      $("story-jira-status").textContent =
        "Select approved stories and enter a valid project key and issue type.";
      return;
    }
    $("story-jira-create").disabled = true;
    $("story-jira-close").disabled = true;
    await work("Creating selected Jira stories…", async () => {
      try {
        const response = await post("jira-stories", {
          request: requestOptions(),
          stories: state.stories,
          project_key: project,
          issue_type: issueType,
          selected_story_ids: selected.map((story) => story.id),
          approved_by: Object.fromEntries(
            selected.map((story) => [story.id, state.acceptedStories.get(story.id).reviewer]),
          ),
        });
        response.results.forEach((result) => state.jiraStories.set(result.story_id, result));
        $("story-jira-status").textContent = response.results.some(
          (result) => result.status !== "created",
        )
          ? "Some creation results are unconfirmed. Check Jira before retrying. Remaining stories were not sent."
          : "Selected approved stories created in Jira.";
      } catch (error) {
        selected.forEach((story) =>
          state.jiraStories.set(story.id, { story_id: story.id, status: "unconfirmed" }),
        );
        $("story-jira-status").textContent = `${error.message} Check Jira before retrying.`;
      }
      $("story-jira-results").replaceChildren();
      state.jiraStories.forEach((result) => {
        const line = document.createElement("p");
        line.textContent = `${result.story_id}: ${result.issue_key || "creation unconfirmed"}`;
        if (result.url && /^https?:\/\//.test(result.url)) {
          const link = document.createElement("a");
          link.href = result.url;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = " Open in Jira";
          line.append(link);
        }
        $("story-jira-results").append(line);
      });
    });
    $("story-jira-create").disabled = !selectedApprovedStories().length;
    $("story-jira-close").disabled = false;
  };
  function storyReviewerError(show) {
    $("stories-accepted-by").classList.toggle("invalid", show);
    $("stories-accepted-by").setAttribute("aria-invalid", String(show));
    $("story-reviewer-error").classList.toggle("hidden", !show);
  }
  $("stories-accepted-by").addEventListener("input", () => storyReviewerError(false));
  $("select-all-stories").addEventListener("change", (event) => {
    document.querySelectorAll(".story-check:not(:disabled)").forEach((checkbox) => {
      checkbox.checked = event.target.checked;
    });
    sync();
  });
  function acceptStories(cards) {
    if (state.busy || activeGeneration || !cards.length) return;
    const reviewer = $("stories-accepted-by").value.trim();
    if (reviewer.length < 2 || reviewer.length > 100) {
      storyReviewerError(true);
      $("stories-accepted-by").focus();
      return;
    }
    storyReviewerError(false);
    cards.forEach((card) => {
      const story = state.stories.stories[Number(card.dataset.storyIndex)];
      if (state.dirtyStories.has(story.id) || state.acceptedStories.has(story.id)) return;
      state.acceptedStories.set(story.id, { reviewer, acceptedAt: new Date().toISOString() });
      card.querySelector(".story-edit-status").textContent = `${story.id} accepted by ${reviewer}.`;
    });
    sync();
    status(
      allStoriesAccepted()
        ? `All stories accepted by reviewers. Continue to scenarios.`
        : "Selected stories accepted. Review the remaining stories.",
    );
  }
  $("accept-selected-stories").onclick = () =>
    acceptStories(
      [...document.querySelectorAll(".story-check:checked:not(:disabled)")].map((checkbox) =>
        checkbox.closest("[data-story-index]"),
      ),
    );
  function discardStoryEdits(card) {
    if (state.busy) return;
    const story = state.stories.stories[Number(card.dataset.storyIndex)];
    card.querySelectorAll("[data-field]").forEach((field) => {
      const value = story[field.dataset.field];
      field.value = Array.isArray(value) ? value.join("\n") : value;
    });
    state.dirtyStories.delete(story.id);
    card.querySelector(".story-dialog-status").textContent = "";
    card.querySelector(".story-edit").close();
    sync();
    card.querySelector(".story-open-edit").focus();
  }
  $("story-cards").addEventListener(
    "cancel",
    (event) => {
      if (!event.target.matches(".story-edit")) return;
      event.preventDefault();
      discardStoryEdits(event.target.closest("[data-story-index]"));
    },
    true,
  );
  $("story-cards").addEventListener("input", (event) => {
    if (event.target.matches(".story-check")) {
      sync();
      return;
    }
    const card = event.target.closest("[data-story-index]");
    if (!card || state.busy) return;
    const story = state.stories.stories[Number(card.dataset.storyIndex)];
    state.dirtyStories.add(story.id);
    card.querySelector(".story-dialog-status").textContent = "Update to save your changes.";
    sync();
  });
  $("story-cards").addEventListener("click", (event) => {
    const card = event.target.closest("[data-story-index]");
    if (!card || state.busy || activeGeneration) return;
    const index = Number(card.dataset.storyIndex);
    const story = state.stories.stories[index];
    if (event.target.closest(".story-accept")) {
      acceptStories([card]);
    }
    if (event.target.closest(".story-open-edit")) {
      card.querySelector(".story-edit").showModal();
    }
    if (event.target.closest(".story-cancel-edit")) discardStoryEdits(card);

    if (event.target.closest(".story-save")) {
      work(`Validating ${story.id} edits…`, async (current) => {
        const edited = editedItems(`[data-story-index="${index}"]`, [story])[0];
        const result = {
          ...state.stories,
          stories: state.stories.stories.map((item, i) => (i === index ? edited : item)),
        };
        try {
          await post("validate-stories", { request: requestOptions(), stories: result });
          current();
        } catch (error) {
          card.querySelector(".story-dialog-status").textContent = error.message;
          throw error;
        }
        card.querySelector(".story-edit").close();
        revision += 1;
        state.stories = result;
        state.acceptedStories.delete(story.id);
        state.dirtyStories.delete(story.id);
        state.storiesReviewed = false;
        invalidate(3);
        card.outerHTML = storyMarkup(edited, index);
        document.querySelector(`[data-story-index="${index}"] .story-open-edit`).focus();
        status(`${story.id} changes saved. Review and accept this story.`);
      });
    }
  });
  function renderScenarios() {
    $("scenario-cards").innerHTML =
      state.scenarios.scenarios
        .map(
          (scenario, index) =>
            `<article class="stage-card" data-scenario-index="${index}">
        <div class="story-review-heading"><span class="chip">${esc(scenario.id)} → ${esc(scenario.story_id)}</span><span class="scenario-review-state">Review required</span></div>
        <h3>${esc(scenario.title)}</h3>
        <p><strong>Preconditions:</strong> ${esc(scenario.preconditions.join("; ") || "None specified")}</p>
        <p><strong>Action:</strong> ${esc(scenario.action)}</p><p><strong>Expected:</strong> ${esc(scenario.expected_result)}</p>
        <ul>${scenario.acceptance_criteria.map((ac) => `<li>${esc(ac)}</li>`).join("")}</ul>
        <button class="secondary scenario-open-edit" type="button" aria-haspopup="dialog">Edit ${esc(scenario.id)}</button>
        <dialog class="story-edit-dialog scenario-edit-dialog" aria-labelledby="scenario-edit-title-${index}">
          <h2 id="scenario-edit-title-${index}">Edit ${esc(scenario.id)}</h2><p>Update the scenario details, or discard to keep the current scenario.</p>
          ${editField("title", "Title", scenario.title)}
          ${editField("preconditions", "Preconditions (one per line)", scenario.preconditions.join("\n"))}
          ${editField("action", "Action", scenario.action)}
          ${editField("expected_result", "Expected result", scenario.expected_result)}
          ${editField("acceptance_criteria", "Covered story acceptance criteria (one per line)", scenario.acceptance_criteria.join("\n"))}
          <div class="story-review-actions"><button class="primary scenario-update" type="button">Update</button><button class="secondary scenario-discard" type="button">Discard</button></div>
          <p class="scenario-dialog-status" role="alert"></p>
        </dialog>
      </article>`,
        )
        .join("") + questions(state.scenarios.open_questions);
    sync();
  }
  function allScenariosAccepted() {
    return (
      Boolean(state.scenarios?.scenarios.length) &&
      !state.dirtyScenarios.size &&
      state.scenarios.scenarios.every((item) => state.acceptedScenarios.has(item.id))
    );
  }
  function scenarioReviewerError(show) {
    $("scenarios-accepted-by").classList.toggle("invalid", show);
    $("scenarios-accepted-by").setAttribute("aria-invalid", String(show));
    $("scenario-reviewer-error").classList.toggle("hidden", !show);
  }
  $("scenarios-accepted-by").addEventListener("input", () => scenarioReviewerError(false));
  $("accept-scenarios").onclick = () => {
    if (state.busy || !state.scenarios) return;
    const reviewer = $("scenarios-accepted-by").value.trim();
    if (reviewer.length < 2 || reviewer.length > 100) {
      scenarioReviewerError(true);
      $("scenarios-accepted-by").focus();
      return;
    }
    scenarioReviewerError(false);
    state.scenarios.scenarios.forEach((item) => state.acceptedScenarios.set(item.id, reviewer));
    state.scenariosReviewed = false;
    sync();
    status(`All scenarios approved by ${reviewer}. Continue to test cases.`);
  };
  $("review-scenarios").onclick = () => {
    if (state.busy || !allScenariosAccepted()) return;
    state.scenariosReviewed = true;
    sync();
    show(4);
    status("Scenarios reviewed. Create test cases using your requirements-stage choices.");
  };
  function discardScenarioEdits(card) {
    if (state.busy) return;
    const scenario = state.scenarios.scenarios[Number(card.dataset.scenarioIndex)];
    card.querySelectorAll("[data-field]").forEach((field) => {
      const value = scenario[field.dataset.field];
      field.value = Array.isArray(value) ? value.join("\n") : value;
    });
    state.dirtyScenarios.delete(scenario.id);
    card.querySelector(".scenario-dialog-status").textContent = "";
    card.querySelector("dialog").close();
    sync();
    card.querySelector(".scenario-open-edit").focus();
  }
  $("scenario-cards").addEventListener("input", (event) => {
    const card = event.target.closest("[data-scenario-index]");
    if (!card || !event.target.matches("[data-field]")) return;
    const scenario = state.scenarios.scenarios[Number(card.dataset.scenarioIndex)];
    state.dirtyScenarios.add(scenario.id);
    state.scenariosReviewed = false;
    card.querySelector(".scenario-dialog-status").textContent = "Update to save your changes.";
    sync();
  });
  $("scenario-cards").addEventListener(
    "cancel",
    (event) => {
      if (!event.target.matches(".scenario-edit-dialog")) return;
      event.preventDefault();
      discardScenarioEdits(event.target.closest("[data-scenario-index]"));
    },
    true,
  );
  $("scenario-cards").addEventListener("click", (event) => {
    const card = event.target.closest("[data-scenario-index]");
    if (!card || state.busy || activeGeneration) return;
    if (event.target.closest(".scenario-open-edit")) card.querySelector("dialog").showModal();
    if (event.target.closest(".scenario-discard")) discardScenarioEdits(card);
    if (event.target.closest(".scenario-update")) {
      const index = Number(card.dataset.scenarioIndex);
      work("Validating scenario edits…", async (current) => {
        const edited = editedItems(`[data-scenario-index="${index}"]`, [
          state.scenarios.scenarios[index],
        ])[0];
        const result = {
          ...state.scenarios,
          scenarios: state.scenarios.scenarios.map((item, i) => (i === index ? edited : item)),
        };
        try {
          await post("validate-scenarios", {
            request: requestOptions(),
            stories: state.stories,
            scenarios: result,
          });
          current();
        } catch (error) {
          card.querySelector(".scenario-dialog-status").textContent = error.message;
          throw error;
        }
        revision += 1;
        card.querySelector("dialog").close();
        state.scenarios = result;
        state.acceptedScenarios.clear();
        state.dirtyScenarios.clear();
        state.scenariosReviewed = false;
        invalidate(4);
        renderScenarios();
        status("Scenario updated. Review and approve all scenarios again.");
      });
    }
  });
  $("stage-stories").onclick = () => {
    if (state.busy || !state.request || allStoriesAccepted()) return;
    return work(
      "Story Agent is converting requirements into stories…",
      async (current) => {
        const result = await post("stories", requestOptions());
        current();
        invalidate(2);
        state.stories = result;
        renderStories();
        status("Stories ready. Review, edit and accept each story to continue.");
      },
      "stories",
    );
  };
  $("review-stories").onclick = () => {
    if (state.busy || !allStoriesAccepted()) return;
    state.storiesReviewed = true;
    sync();
    show(3);
    status("Stories reviewed. Create scenario coverage for these requirements.");
  };
  $("stage-scenarios").onclick = () =>
    work(
      "Scenario Agent is designing story coverage…",
      async (current) => {
        const result = await post("scenarios", {
          request: requestOptions(),
          stories: state.stories,
        });
        current();
        invalidate(3);
        state.scenarios = result;
        renderScenarios();
        status("Scenarios ready. Review or edit them before creating test cases.");
      },
      "scenarios",
    );
  $("stage-cases").onclick = () =>
    work(
      "Test Case Agent is generating and validating cases…",
      async (current) => {
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
      },
      "test-cases",
    );
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
    work("Loading feature execution plan…", refreshExecution, "execution-plan");
  };
  $("stage-refresh-execution").onclick = () =>
    work("Refreshing feature execution plan…", refreshExecution, "execution-plan");
  $("stage-run").onclick = () =>
    work(
      "ReqnRoll run in progress. Waiting for actual case results…",
      async (current) => {
        state.runReport = null;
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
      },
      "execution",
    );
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
