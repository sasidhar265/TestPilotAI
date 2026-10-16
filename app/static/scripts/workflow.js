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
  let savedBaReport = null;
  let savedRequirementsReport = null;
  const tabs = [...document.querySelectorAll("[data-stage]")];
  const workspace = document.querySelector(".stage-workspace");
  workspace.before(document.querySelector(".studio-layout"));
  $("stage-panel-4").insertBefore($("results"), $("review-cases"));
  const status = (message) => {
    $("stage-status").textContent = message;
    $("status").textContent = message;
  };
  function show(stage, focus = true) {
    const view = window.workflowStages[stage - 1].view;
    const targetUrl = window.workflowStageUrl(view);
    if (window.roleCanNavigate && !window.roleCanNavigate(targetUrl)) return;
    if (window.navigateWorkspace && (location.pathname !== "/" || document.body.dataset.qualityView !== view)) {
      window.navigateWorkspace(targetUrl, focus);
      if (focus) tabs[stage - 1].focus({ preventScroll: true });
      return;
    }
    state.stage = stage;
    workspace.hidden = stage === 1 || stage === 6;
    tabs.forEach((tab, index) => {
      const active = index + 1 === stage;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      const panel = $(`stage-panel-${index + 1}`);
      if (panel) panel.hidden = !active;
      if (active && focus) tab.focus({ preventScroll: true });
      const strip = tab.parentElement;
      if (active && strip.getClientRects().length && strip.scrollWidth > strip.clientWidth) {
        const left = tab.offsetLeft - strip.offsetLeft;
        if (left < strip.scrollLeft) strip.scrollLeft = left;
        else if (left + tab.offsetWidth > strip.scrollLeft + strip.clientWidth)
          strip.scrollLeft = left + tab.offsetWidth - strip.clientWidth;
      }
    });
    if (stage === 5 && suite) {
      work("Loading feature execution plan…", refreshExecution, "execution-plan");
    }
  }
  tabs.forEach((tab, index) => {
    tab.onclick = () => show(index + 1, false);
    tab.onkeydown = (event) => {
      const available = tabs.filter(item => !item.hasAttribute("data-role-hidden"));
      const position = available.indexOf(tab);
      const next = { ArrowRight: (position + 1) % available.length, ArrowLeft: (position + available.length - 1) % available.length, Home: 0, End: available.length - 1 }[event.key];
      if (next !== undefined) {
        event.preventDefault();
        show(tabs.indexOf(available[next]) + 1);
      }
    };
  });
  function emptyOutput(title, description, stage, action) {
    return `<div class="stage-empty"><span class="stage-empty-icon" aria-hidden="true">◇</span>
      <h3>${esc(title)}</h3><p>${esc(description)}</p>
      <button class="secondary" type="button" data-open-stage="${stage}">${esc(action)} →</button></div>`;
  }
  workspace.addEventListener("click", (event) => {
    const action = event.target.closest("[data-open-stage]");
    if (action) show(Number(action.dataset.openStage));
  });
  function outcomeClass(value) {
    return (
      {
        passed: "passed",
        failed: "failed",
        error: "failed",
        blocked: "blocked",
        skipped: "skipped",
        notexecuted: "skipped",
        "not-run": "skipped",
      }[String(value).toLowerCase()] || "unknown"
    );
  }
  function sync() {
    document.querySelector(".story-approval-toolbar").hidden = !state.stories;
    document.querySelector(".scenario-approval-toolbar").hidden = !state.scenarios;
    if (!suite && !$("stage-execution-list").children.length) {
      $("stage-execution-list").innerHTML = emptyOutput(
        "Prepare your first test run",
        "Create and review test cases to see the execution plan and available actions.",
        4,
        "Review test cases",
      );
    }
    workspace.hidden = state.stage === 1 || state.stage === 6;
    syncGenerateAvailability();
    $("generate").disabled ||= state.busy;
    $("validate-requirements").disabled = state.busy || Boolean(activeGeneration);
    $("ba-review").disabled = state.busy || Boolean(activeGeneration);
    $("stage-stories").disabled = state.busy || !state.request || Boolean(state.stories);
    $("stage-stories").textContent = state.stories ? "Stories created ✓" : "Create stories →";
    $("stage-stories").title = state.stories
      ? "Stories are already created. Change the requirements to create new stories."
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
    $("stage-scenarios").disabled =
      state.busy || !state.storiesReviewed || Boolean(state.scenarios);
    $("stage-scenarios").textContent = state.scenarios
      ? "Scenarios created ✓"
      : "Create scenarios →";
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
    $("stage-cases").disabled = state.busy || !state.scenariosReviewed || Boolean(suite);
    $("stage-cases").textContent = suite ? "Test cases created ✓" : "Create test cases →";
    $("review-cases").disabled = state.busy || !suite;
    $("stage-refresh-execution").disabled = state.busy || !suite;
    $("stage-run").disabled = state.busy || !state.plan?.ready;
    const outputCounts = [
      null,
      state.stories?.stories.length,
      state.scenarios?.scenarios.length,
      suite?.test_cases.length,
      null,
    ];
    tabs.forEach((tab, i) => {
      const badge = tab.querySelector(".stage-count");
      badge.hidden = outputCounts[i] == null;
      badge.textContent = outputCounts[i] ?? "";
    });
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
    savedRequirementsReport = null;
    $("requirements-validation-report").hidden = true;
    if (from <= 1) state.request = null;
    if (from <= 2) {
      state.stories = null;
      state.storiesReviewed = false;
      $("story-cards").innerHTML = emptyOutput(
        "Your stories will appear here",
        "Generate stories from your current requirements.",
        1,
        "Review requirements",
      );
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
      $("scenario-cards").innerHTML = emptyOutput(
        "Build coverage from approved stories",
        "Review and approve stories before creating scenarios.",
        2,
        "Review stories",
      );
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
  let latestBrdText = null;
  function sourceChanged() {
    savedBaReport = null;
    savedRequirementsReport = null;
    revision += 1;
    syncAgentWorkflow();
    latestBrdText = null;
    $("ba-report").hidden = true;
    $("ba-status").textContent = "Source changed. Run BA review again for the current input.";
    $("requirements-validation-report").hidden = true;
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
  ["finance-domain-product", "finance-domain-journey"].forEach((id) =>
    $(id)?.addEventListener("change", sourceChanged),
  );
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
    let outcome = "Completed";
    try {
      await task(current);
    } catch (error) {
      outcome = operation?.cancelled ? "Cancelled" : "Failed";
      status(operation?.cancelled ? `${generationStages[kind].label} cancelled.` : error.message);
      if (kind === "ba-review") $("ba-status").textContent = operation?.cancelled ? "BA review cancelled." : error.message;
    } finally {
      if (operation) {
        await stopLifecycleFeed(operation.requestId);
        finishAgentWorkflow(outcome);
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
  const post = async (path, body) => {
    const result = await (await api(`/api/workflow/${path}`, body, transportOptions())).json();
    if (["ba-review", "stories", "scenarios", "test-cases"].includes(path)) recordOperationResult(path, result);
    if (path === "execution-plan") recordOperationResult(path, result);
    if (path === "execute") recordOperationResult("execution", result);
    if (path === "test-cases") recordSuiteValidation(result.validation, result.suite);
    return result;
  };
  function requestOptions() {
    const target = selectedGenerationTarget();
    return {
      ...state.request,
      finance_calculation: window.financeCalculationContext?.() || null,
      finance_product_id: $("finance-domain-product")?.value || null,
      finance_journey_ids: $("finance-domain-journey")?.value
        ? [$("finance-domain-journey").value]
        : [],
      generation_target: target,
      output_format: target === "manual" ? "normal" : "bdd",
      manual_testing_type: $("manual-testing-type").value,
      llm_model: $("llm-model").value || "auto-fallback",
    };
  }
  async function readRequirementSource(current) {
    let description = $("description").value.trim();
    let uploadedBrdText = null;
    let uploadedBrdReceipt = null;
    const selected = attachedFile;
    if (selected) {
      const form = new FormData();
      form.append("file", selected);
      const result = await (
        await upload("/api/workflow/requirements/document", form, transportOptions())
      ).json();
      current();
      description = description.endsWith(result.description)
        ? description
        : [description, result.description].filter(Boolean).join("\n\n");
      uploadedBrdText = result.description;
      uploadedBrdReceipt = result.uploaded_brd_receipt;
      latestBrdText = uploadedBrdText;
    }
    if (description.length < 10)
      throw new Error("Enter at least 10 characters or attach a readable BRD.");
    if (description.length > 30000)
      throw new Error("Split the requirements into batches of at most 30,000 characters.");
    current();
    await resolveBusinessRules({ ...transportOptions(), persistShared: false });
    current();
    return {
      description,
      business_rules: parseBusinessRules(),
      llm_model: $("llm-model").value || "auto-fallback",
      additional_context: $("sdlc-constraints")?.value || "",
      finance_calculation: window.financeCalculationContext?.() || null,
      finance_product_id: $("finance-domain-product")?.value || null,
      finance_journey_ids: $("finance-domain-journey")?.value
        ? [$("finance-domain-journey").value]
        : [],
      uploaded_brd_text: uploadedBrdText,
      uploaded_brd_receipt: uploadedBrdReceipt,
    };
  }
  window.prepareSdlcRequirements = async () => {
    const source = await readRequirementSource(() => {});
    const request = { ...requestOptions(), ...source };
    if (!attachedFile && state.request?.description === request.description) {
      request.uploaded_brd_text = state.request.uploaded_brd_text || null;
      request.uploaded_brd_receipt = state.request.uploaded_brd_receipt || null;
    }
    if (JSON.stringify(state.request) !== JSON.stringify(request)) invalidate(2);
    state.request = request;
    $("description").value = request.description;
    return request;
  };
  function renderRequirementsValidation(report) {
    savedRequirementsReport = report;
    recordReturnedEvidence("Requirements Validation Agent", report.status,
      `Returned alignment report: ${report.message} Regulatory compliance: ${report.regulatory_compliance || "not assessed"}.`,
      (report.sources || []).map((s) => `${s.title || s.id} · ${s.id} · v${s.version || "not supplied"}`));
    const panel = $("requirements-validation-report");
    panel.hidden = false;
    panel.dataset.status = report.status;
    const brdText =
      latestBrdText || (attachedFile ? Object.values(report.requirements || {}).join("\n") : "");
    const findings = (report.findings || []).filter((finding) => finding.status !== "aligned");
    const suggestions = findings
      .map(
        (finding) =>
          `<li><b>${esc(finding.requirement_id)} · ${esc(finding.status)}</b><p>${esc(finding.reason)}</p><p><strong>Suggested fix:</strong> ${esc(finding.suggested_change || "Review this requirement with the business owner and clarify the expected behavior.")}</p>${(finding.evidence || []).map((source) => `<blockquote>${esc(source.source_id)}: ${esc(source.quote)}</blockquote>`).join("")}</li>`,
      )
      .join("");
    const uploadHelp = report.message.includes("verification failed")
      ? "The uploaded document could not be verified. Re-upload the BRD and validate again."
      : "Review the suggested changes with the business owner, update the BRD, then upload it and validate again.";
    const showDraft = report.status === "blocked" && Boolean(brdText);
    panel.innerHTML = `<strong>${esc(report.message)}</strong>${report.status === "blocked" ? `<div class="requirements-fix-guidance"><h4>How to fix the BRD</h4><p>${esc(uploadHelp)}</p>${suggestions ? `<ul>${suggestions}</ul>` : ""}</div>` : ""}${showDraft ? `<div class="requirements-draft-actions"><button type="button" class="secondary" id="preview-brd-draft" aria-expanded="false" aria-controls="brd-draft-preview">Preview proposed BRD</button><button type="button" class="secondary" id="download-brd-draft">Download proposed BRD</button></div><div id="brd-draft-preview" hidden><label for="brd-draft-text">Proposed BRD draft · review and edit before download</label><textarea id="brd-draft-text" spellcheck="true"></textarea><small>Suggestions are review notes. The extracted requirement text is preserved until you edit this draft.</small></div>` : ""}<small>Business alignment assessment · Regulatory compliance not assessed.</small>`;
    if (showDraft) {
      const notes = findings
        .map(
          (finding) =>
            `### ${finding.requirement_id} · ${finding.status}\nCurrent requirement: ${report.requirements?.[finding.requirement_id] || "See the original BRD"}\nReason: ${finding.reason}\nSuggested fix: ${finding.suggested_change || "Clarify the expected behavior with the business owner."}`,
        )
        .join("\n\n");
      const draft = `# Proposed BRD revision\n\n## Extracted requirements\n\n${brdText}\n\n## Validation review notes\n\n${notes || uploadHelp}\n`;
      const preview = panel.querySelector("#brd-draft-preview");
      panel.querySelector("#brd-draft-text").value = draft;
      panel.querySelector("#preview-brd-draft").onclick = (event) => {
        preview.hidden = !preview.hidden;
        event.currentTarget.setAttribute("aria-expanded", String(!preview.hidden));
        if (!preview.hidden) panel.querySelector("#brd-draft-text").focus();
      };
      panel.querySelector("#download-brd-draft").onclick = () => {
        const draftText = panel.querySelector("#brd-draft-text").value;
        if (!draftText.trim() || draftText.length > 50000) {
          status("The proposed BRD must contain 1 to 50,000 characters before download.");
          return;
        }
        try {
          BrdPdf.download(
            draftText,
            `${(attachedFile?.name || "requirements").replace(/\.[^.]+$/, "")}-proposed-brd.pdf`,
          );
        } catch {
          status("The PDF could not be created. Try a shorter BRD draft.");
        }
      };
    }
    if (report.status !== "aligned") {
      state.plan = null;
      sync();
    }
  }
  window.addEventListener("requirements-validation", (event) => {
    renderRequirementsValidation(event.detail);
    if (event.detail.status === "blocked") {
      window.navigateWorkspace("/?view=requirements", false);
      $("requirements-validation-report").closest("details").open = true;
    }
  });
  function renderBaReport(report) {
    savedBaReport = report;
    recordReturnedEvidence("BA Agent review", "reported",
      `Returned BA review outcome: ${report.outcome}. Business approval: ${report.business_approval}; regulatory compliance: ${report.regulatory_compliance}. Detailed check events were not received; this displays the final response.`,
      [ `Document: ${report.document_fingerprint}. Knowledge: ${report.knowledge_fingerprint}.`,
        ...(report.knowledge_sources || []).map((s) => `${s.title} · ${s.id} · v${s.version} · ${s.authority} (available source; citation not inferred)`)]);
    const list = (items) => `<ul>${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`;
    const label = (value) => String(value).replaceAll("_", " ");
    const sourceMap = new Map(report.knowledge_sources.map(source => [source.id, source]));
    const domain = report.domain_validation;
    const domainChecks = report.domain_checks || [];
    if (domain) recordReturnedEvidence("BA domain validation",
      domain.status === "needs_clarification" ? "failed" : domain.status === "covered" ? "passed" : "reported",
      `UK guide domain review: ${domain.topics_reviewed} topics reviewed; ${domain.covered} covered, ${domain.gaps} gaps, ${domain.conflicts} potential conflicts, ${domain.not_applicable} outside scope. This is reference guidance, not business approval.`,
      domainChecks.flatMap(check => check.evidence.map(item => `${item.source_id}: ${item.quote}`)), true);
    const blockers = report.findings.filter(finding => finding.severity === "blocker").length;
    const majors = report.findings.filter(finding => finding.severity === "major").length;
    const knowledgeIncomplete = (domain?.alignment_unassessable || 0) > 0 || report.knowledge_limitations.length > 0;
    const businessFit = report.outcome === "blocked" || blockers ? "Blocked for business review"
      : report.outcome !== "ready_for_business_review" || majors || domain?.gaps || domain?.conflicts || report.areas.some(area => area.status === "gap") || report.open_questions.length
        ? "Needs refinement" : knowledgeIncomplete ? "Provisional fit — knowledge incomplete" : "Ready for business review";
    const alignmentHtml = `<section class="ba-alignment-summary" aria-label="BRD alignment and business fit">
      <div class="ba-summary-grid"><article><span class="section-kicker">Domain alignment</span>
      <h3>${domain?.alignment_percent == null ? "Not assessable" : `${esc(domain.alignment_percent)}%`}</h3>
      <p>${esc(domain?.covered || 0)} covered / ${esc(domain?.alignment_assessable || 0)} assessable in-scope topics.</p>
      <p class="field-help">${esc(domain?.alignment_method || "Alignment score was not reported. Rerun BA review.")} Outside-scope topics are excluded. Missing knowledge is unassessable, rather than a BRD failure.</p>
      <p>${esc(domain?.alignment_unassessable || 0)} topics cannot be assessed because domain knowledge is missing.</p></article>
      <article><span class="section-kicker">Business fit</span><h3>${esc(businessFit)}</h3>
      <p>${esc(blockers)} blockers · ${esc(majors)} major findings · ${esc(report.open_questions.length)} open questions.</p>
      <p class="field-help">Based on the scoped BA outcome, review-area gaps and findings. This assesses requirements readiness, not commercial suitability or business approval.</p>
      ${knowledgeIncomplete ? "<p class='field-help'>Knowledge limitations remain; even 100% alignment is limited to the available references.</p>" : ""}</article></div></section>`;
    const domainHtml = `<section class="ba-domain-validation" aria-label="Auto-finance domain validation report">
      <div class="panel-head"><h3>Auto-finance domain validation</h3><div class="story-review-actions"><button type="button" class="secondary" id="open-ba-validation-report">Open report ↗</button><button type="button" class="secondary" id="download-ba-validation-report">Download HTML report</button></div></div>
      ${domain ? `<p><strong>${esc(label(domain.status))}</strong> · ${esc(domain.topics_reviewed)} relevant guide topics assessed.</p>
      <div class="ba-domain-metrics"><span>${esc(domain.covered)} covered</span><span>${esc(domain.gaps)} gaps</span><span>${esc(domain.conflicts)} potential conflicts</span><span>${esc(domain.not_applicable)} outside scope</span></div>` : "<p>No domain validation summary was returned. Run BA review again for topic-level validation.</p>"}
      <p class="field-help">Uses the same reference content as the UK finance guide. Public guidance identifies review questions; approved business policies retain their separate authority.</p>
      <p class="field-help">Review product: ${esc(report.domain_scope?.product || "Unspecified")} · Vehicle: ${esc(report.domain_scope?.vehicle_condition || "Unspecified")} · Functionality: ${esc(report.domain_scope?.journeys?.join(", ") || "Unspecified")}</p>
      <details class="ba-scope-summary"><summary>Scope used for this review</summary>${list(report.domain_scope?.scope_basis || [])}<p>Excluded functionality is not reported as missing.</p>${list(report.domain_scope?.excluded_journeys || [])}</details>
      ${domainChecks.map(check => `<details class="ba-domain-check" data-domain-topic="${esc(check.topic_id)}"><summary><span class="chip">${esc(label(check.status))}</span> ${esc(sourceMap.get(check.topic_id)?.title || check.topic_id)}</summary>
        <p><strong>Points considered:</strong> ${esc(check.reason)}</p><p><strong>Recommendation:</strong> ${esc(check.recommendation)}</p>
        ${check.status === "gap" ? `<p><strong>Gap in:</strong> ${esc(label(check.gap_origin || "brd"))}</p>` : ""}
        ${check.document_quote ? `<blockquote><strong>BRD excerpt:</strong> ${esc(check.document_quote)}</blockquote>` : "<p class='field-help'>No BRD excerpt was reported for this check.</p>"}
        ${check.evidence.map(item => `<blockquote><strong>${esc(item.source_id)}</strong>: ${esc(item.quote)}</blockquote>`).join("")}
        <p class="field-help">Topic: <code>${esc(check.topic_id)}</code> · Source: <code>${esc(sourceMap.get(check.topic_id)?.path || "Not reported")}</code> · Reference only</p>
      </details>`).join("")}</section>`;
    $("ba-report").hidden = false;
    $("ba-report").innerHTML = `<div class="ba-outcome"><span class="section-kicker">Review outcome</span><h3>${esc(label(report.outcome))}</h3><time>${esc(new Date(report.assessed_at).toLocaleString())}</time></div>
      <h3>BRD summary</h3><p>${esc(report.summary)}</p>
      ${alignmentHtml}
      ${domainHtml}
      <div class="ba-summary-grid"><div><h3>Business objectives</h3>${list(report.objectives)}</div><div><h3>Document scope</h3>${list(report.scope)}</div></div>
      <h3>BRD review areas</h3><div class="ba-area-grid">${report.areas.map((area) => `<article><span class="chip">${esc(label(area.status))}</span><h4>${esc(label(area.area))}</h4><p>${esc(area.reason)}</p>${area.document_quote ? `<blockquote>${esc(area.document_quote)}</blockquote>` : ""}</article>`).join("")}</div>
      <h3>Findings &amp; recommendations</h3>${report.findings.length ? report.findings.map((finding) => `<article class="ba-finding"><span class="chip">${esc(finding.severity)}</span><h4>${esc(finding.title)}</h4><p>${esc(finding.reason)}</p><p><strong>Recommendation:</strong> ${esc(finding.recommendation)}</p>${finding.document_quote ? `<blockquote>${esc(finding.document_quote)}</blockquote>` : ""}${finding.evidence.map((source) => `<blockquote><strong>${esc(source.source_id)}</strong>: ${esc(source.quote)}</blockquote>`).join("")}</article>`).join("") : "<p>No document-specific findings returned.</p>"}
      <div class="ba-summary-grid"><div><h3>Questions for the business owner</h3>${list(report.open_questions)}</div><div><h3>Next steps</h3>${list(report.next_steps)}</div></div>
      <details><summary>Knowledge considered &amp; review traceability</summary>${report.knowledge_sources.map((source) => `<p><strong>${esc(source.title)}</strong> · ${esc(source.id)} · ${esc(source.version)} · ${esc(label(source.authority))} · ${esc(source.owner)}</p>`).join("")}${list(report.knowledge_limitations)}<p>Document: <code>${esc(report.document_fingerprint)}</code></p><p>Knowledge: <code>${esc(report.knowledge_fingerprint)}</code></p></details>
      <p class="field-help">BA review supports business decisions. Business approval has not been granted; regulatory compliance has not been assessed.</p>`;
    $("ba-status").textContent = `BA review complete: ${label(report.outcome)}.`;
    const exportReport = (openInTab) => {
      const content = $("ba-report").cloneNode(true);
      content.querySelectorAll("button").forEach(button => button.remove());
      content.querySelectorAll("details").forEach(details => { details.open = true; });
      const html = `<!doctype html><html lang="en"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>BA review report</title><style>
        *{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#203247;font:15px/1.65 system-ui,sans-serif}
        main{max-width:1080px;margin:36px auto;padding:36px;background:white;border:1px solid #dce4ed;border-radius:16px}
        header{border-bottom:1px solid #dce4ed;padding-bottom:20px;margin-bottom:24px}h1{margin:0;font-size:30px}h3{margin:24px 0 10px}h4{margin:10px 0}
        header p,.field-help,time{color:#596b7d;font-size:13px}.section-kicker{color:#536980;font-size:12px;text-transform:uppercase;letter-spacing:.08em}
        .ba-summary-grid,.ba-area-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
        article,details,.ba-domain-validation{border:1px solid #dce4ed;border-radius:10px;padding:18px;margin:14px 0;break-inside:avoid}
        summary{font-weight:650;cursor:pointer}.chip,.ba-domain-metrics span{display:inline-block;background:#edf4fa;border-radius:6px;padding:4px 9px;font-size:12px;margin:4px 6px 4px 0}
        blockquote{margin:14px 0;padding:12px 16px;border-left:3px solid #29828b;background:#f3f8fa;white-space:pre-wrap}
        code{overflow-wrap:anywhere;font-size:12px}p,li{overflow-wrap:anywhere}.panel-head h3{margin-top:0}
        @media(max-width:640px){main{margin:12px;padding:20px}.ba-summary-grid,.ba-area-grid{grid-template-columns:1fr}h1{font-size:25px}}
        @media print{body{background:white}main{margin:0;padding:0;border:0}details>summary{list-style:none}@page{size:A4;margin:18mm}}
        </style></head><body><main><header><h1>Business analysis review report</h1><p>BRD assessment, scoped domain checks, recommendations and source evidence.</p></header>${content.innerHTML}</main></body></html>`;
      const url = URL.createObjectURL(new Blob([html], {type:"text/html;charset=utf-8"}));
      const link = document.createElement("a"); link.href = url;
      if (openInTab) { link.target = "_blank"; link.rel = "noopener"; }
      else link.download = "BA-auto-finance-validation-report.html";
      link.click(); setTimeout(() => URL.revokeObjectURL(url), openInTab ? 60000 : 1000);
    };
    $("download-ba-validation-report").onclick = () => exportReport(false);
    $("open-ba-validation-report").onclick = () => exportReport(true);
  }
  $("ba-review").onclick = () => work("BA Agent is reviewing the BRD…", async (current) => {
    $("ba-report").hidden = true;
    $("ba-status").textContent = "BA Agent is reviewing scope, domain knowledge and testability…";
    const source = await readRequirementSource(current);
    try {
      const report = await post("ba-review", {...source, llm_model: $("llm-model").value || "auto-fallback"});
      current(); renderBaReport(report);
    } catch (error) {
      $("ba-status").textContent = error.message;
      throw error;
    }
  }, "ba-review");
  $("validate-requirements").onclick = () =>
    work("Validating business alignment…", async (current) => {
      $("requirements-validation-report").hidden = true;
      const source = await readRequirementSource(current);
      const report = await post("validate-requirements", {
        ...source,
        generation_target: selectedGenerationTarget(),
      });
      current();
      renderRequirementsValidation(report);
      status(report.message);
    });
  $("generate-form").addEventListener(
    "submit",
    (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      window.startRequirementsDelivery?.();
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
      <blockquote><span class="output-field-label">Source requirement</span>${esc(story.source_excerpt)}</blockquote><strong class="output-field-label">Acceptance criteria</strong>
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
        <dl class="scenario-facts">
          <div><dt>Preconditions</dt><dd>${esc(scenario.preconditions.join("; ") || "None specified")}</dd></div>
          <div><dt>Action</dt><dd>${esc(scenario.action)}</dd></div>
          <div class="scenario-expected"><dt>Expected result</dt><dd>${esc(scenario.expected_result)}</dd></div>
        </dl><strong class="output-field-label">Acceptance criteria covered</strong>
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
        if (result.generation_source === "organizational-memory") {
          showKnowledgeNotice({ ...result, knowledge_stage: "stories" });
        }
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
        if (result.generation_source === "organizational-memory") {
          showKnowledgeNotice({ ...result, knowledge_stage: "scenarios" });
        }
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
    $("stage-execution-list").innerHTML =
      (state.plan?.cases || [])
        .map(
          (item) =>
            `<article class="stage-card"><span class="chip">${esc(item.feature_file)}</span><h3>${esc(item.scenario)}</h3><p>${running ? "Submitted to runner · individual progress unavailable until results return" : esc(state.plan?.runStatus || (state.plan?.ready ? "Listed in configured project · not run" : "Not run · target configuration required"))}</p></article>`,
        )
        .join("") ||
      emptyOutput(
        "No automation cases listed",
        "Review the execution plan above for configuration or coverage details.",
        4,
        "Review test cases",
      );
  }
  async function refreshExecution(current) {
    state.plan = null;
    $("stage-execution-list").replaceChildren();
    $("stage-execution-reason").textContent = "Loading the execution plan…";
    manualMarkup();
    if (!suite.test_cases.some((item) => item.execution_mode === "automation")) {
      state.plan = null;
      state.runReport = null;
      $("stage-execution-list").replaceChildren();
      $("stage-execution-reason").textContent = "This suite contains manual cases only.";
      return;
    }
    let result;
    try {
      result = await post("execution-plan", { suite, request: reviewSourceRequest });
    } catch (error) {
      $("stage-execution-reason").textContent =
        "The execution plan could not be loaded. Re-enter this stage or use Refresh execution plan to retry.";
      throw error;
    }
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
  };
  $("stage-refresh-execution").onclick = () =>
    work("Refreshing feature execution plan…", refreshExecution, "execution-plan");
  function renderRunReport(report) {
          $("stage-execution-results").innerHTML =
            `<div class="run-result-heading"><div><span class="section-kicker">LATEST RUN</span><h3>Execution results</h3></div><span class="outcome-badge ${outcomeClass(report.status)}">${esc(report.status)}</span></div>
            <dl class="run-result-metrics"><div><dt>Passed</dt><dd>${esc(report.passed ?? "—")}</dd></div><div><dt>Failed</dt><dd>${esc(report.failed ?? "—")}</dd></div><div><dt>Skipped</dt><dd>${esc(report.skipped ?? "—")}</dd></div></dl>` +
            (report.test_results || [])
              .map(
                (item) =>
                  `<div class="stage-result"><div><span>${esc(item.name)}</span>${item.error ? `<details class="result-failure"><summary>Failure details</summary><pre>${esc(item.error)}</pre></details>` : ""}</div><strong class="outcome-badge ${outcomeClass(item.status)}">${esc(item.status)}</strong></div>`,
              )
              .join("") +
            (report.error ? `<p class="run-result-error">${esc(report.error)}</p>` : "");
          $("stage-execution-results").insertAdjacentHTML(
            "beforeend",
            `<details><summary>Runner output</summary><pre class="stage-run-output">${esc(report.output || "No additional output")}</pre></details>`,
          );
  }
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
          state.runReport = report;
          renderRunReport(report);
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
    $("stage-execution-reason").textContent =
      "The execution plan loads automatically when you enter this stage.";
    $("stage-case-empty").hidden = true;
    if (!restoringDraft) show(4, false);
    sync();
  });
  window.addEventListener("workspace-page-changed", (event) => {
    const stages = { requirements: 1, stories: 2, scenarios: 3, "test-cases": 4, execution: 5, automation: 6 };
    if (event.detail.path === "/" && stages[event.detail.view]) show(stages[event.detail.view], false);
  });
  window.workflowApprovalContext = () => state.request && state.stories ? {
    request: state.request, stories: state.stories, ...(state.scenarios ? {scenarios:state.scenarios} : {}),
    story_approvals: Object.fromEntries([...state.acceptedStories].map(([id, value]) => [id, value.reviewer])),
    scenario_approvals: Object.fromEntries(state.acceptedScenarios),
    ...(savedBaReport ? {ba_report:savedBaReport} : {}),
    ...(savedRequirementsReport ? {requirements_report:savedRequirementsReport} : {}),
  } : null;
  // Tab-scoped, account-scoped recovery for links that load another document.
  let draftKey = null;
  let restoringDraft = false;
  const draftControls = ["sdlc-constraints", "sdlc-target", "description", "business-rules", "finance-domain-product", "finance-domain-journey", "manual-testing-type", "llm-model", "generation-target"];
  function workspaceSnapshot() {
    const controls = Object.fromEntries(draftControls.filter(id => $(id)).map(id => [id, $(id).value]));
    return { version: 1, controls, state: {...state, busy:false,
      acceptedStories:[...state.acceptedStories], jiraStories:[...state.jiraStories],
      dirtyStories:[...state.dirtyStories], acceptedScenarios:[...state.acceptedScenarios],
      dirtyScenarios:[...state.dirtyScenarios]}, suite, validationReport, reviewSourceRequest,
      executionSummary, stepDefinitionArtifact, savedBaReport, savedRequirementsReport, latestBrdText,
      editorDrafts: [...document.querySelectorAll('[data-story-index] textarea, [data-scenario-index] textarea')].map(control => ({
        kind: control.closest('[data-story-index]') ? 'story' : 'scenario',
        index: control.closest('[data-story-index], [data-scenario-index]').dataset.storyIndex ?? control.closest('[data-scenario-index]').dataset.scenarioIndex,
        field: control.dataset.field, value: control.value,
      })),
      caseSelections: [...document.querySelectorAll("#cases .case-check")].map(control => control.checked) };
  }
  window.exportTestingWorkspace = workspaceSnapshot;
  window.testingWorkspaceBusy = () => state.busy || Boolean(activeGeneration);
  function saveWorkspaceDraft() {
    if (!draftKey || restoringDraft) return;
    try { sessionStorage.setItem(draftKey, JSON.stringify(workspaceSnapshot())); }
    catch { /* Project persistence remains available if browser storage is full. */ }
  }
  window.addEventListener("pagehide", saveWorkspaceDraft);
  window.addEventListener("workspace-page-changed", saveWorkspaceDraft);
  document.addEventListener("click", event => {
    if (event.target.closest("a[href]")) saveWorkspaceDraft();
  });
  window.restoreTestingWorkspace = (draft) => {
    if (state.busy || activeGeneration) throw new Error("Wait for generation to finish before restoring a project");
    restoringDraft = true;
    try {
      if (draft.version !== 1 || !draft.state) throw new Error("Unsupported workspace snapshot");
      for (const [id, value] of Object.entries(draft.controls || {})) if ($(id)) $(id).value = value;
      invalidate(1);
      savedBaReport = null;
      $("ba-report").hidden = true;
      if (draft.suite) render(draft.suite);
      Object.assign(state, draft.state, {busy:false});
      for (const name of ["acceptedStories", "jiraStories", "acceptedScenarios"]) state[name] = new Map(draft.state[name]);
      for (const name of ["dirtyStories", "dirtyScenarios"]) state[name] = new Set(draft.state[name]);
      document.querySelectorAll("#cases .case-check").forEach((control, index) => {
        if (draft.caseSelections?.[index] !== undefined) control.checked = draft.caseSelections[index];
      });
      validationReport = draft.validationReport;
      reviewSourceRequest = draft.reviewSourceRequest;
      executionSummary = draft.executionSummary;
      latestBrdText = draft.latestBrdText;
      if (state.stories) renderStories();
      if (state.scenarios) renderScenarios();
      for (const edit of draft.editorDrafts || []) {
        const card = [...document.querySelectorAll(`[data-${edit.kind}-index]`)].find(card => card.dataset[`${edit.kind}Index`] === String(edit.index));
        const control = card && [...card.querySelectorAll('textarea')].find(control => control.dataset.field === edit.field);
        if (control) control.value = edit.value;
      }
      if (draft.savedBaReport) renderBaReport(draft.savedBaReport);
      if (draft.savedRequirementsReport) renderRequirementsValidation(draft.savedRequirementsReport);
      if (draft.stepDefinitionArtifact) renderStepDefinitions(draft.stepDefinitionArtifact);
      if (state.plan) renderPlan();
      if (suite) manualMarkup();
      if (state.runReport) renderRunReport(state.runReport);
      if (location.pathname === "/") show(({stories:2,scenarios:3,"test-cases":4,execution:5,automation:6})[document.body.dataset.qualityView] || 1, false);
      sync();
    } finally { restoringDraft = false; }
    saveWorkspaceDraft();
  };
  window.loadWorkspaceProfile().then(profile => {
    if (!profile.username || profile.is_guest) return;
    draftKey = `quality-workspace-draft:v1:${profile.username}`;
    const stored = sessionStorage.getItem(draftKey);
    if (!stored || state.busy || activeGeneration || state.request || savedBaReport) return;
    restoringDraft = true;
    try {
      window.restoreTestingWorkspace(JSON.parse(stored));
      status("Restored your workspace results and feedback from this browser tab.");
    } catch { sessionStorage.removeItem(draftKey); }
    finally { restoringDraft = false; }
  }).catch(() => {});
  const initialStages = { stories: 2, scenarios: 3, "test-cases": 4, execution: 5, automation: 6 };
  if (location.pathname === "/") show(initialStages[document.body.dataset.qualityView] || 1, false);
  sync();
})();
