/* Sequential SDLC workspace. All stages, groups and destinations come from backend policy. */
(() => {
  const host = document.getElementById("sdlc-content");
  if (!host) return;
  const section = document.createElement("section");
  section.className = "sdlc-sequence";
  section.setAttribute("aria-label", "SDLC workflow navigation");
  section.innerHTML = `<p id="sdlc-sequence-position" role="status" hidden></p>
    <div id="sdlc-phase-tabs" class="sdlc-phase-navigation" aria-label="SDLC stages"></div>
    <section id="sdlc-step-panel" role="region" tabindex="0"><span id="sdlc-step-number" class="section-kicker"></span><div class="sdlc-heading-with-info"><h3 id="sdlc-step-heading"></h3><button type="button" id="requirements-info" class="requirements-info" popovertarget="sdlc-responsibilities" aria-label="Requirements responsibilities and handoff information" hidden>i</button></div><p id="sdlc-step-description"></p>
    <p id="sdlc-step-view-note" role="status"></p>
    <section id="sdlc-responsibilities" class="delivery-responsibilities" aria-label="AI and human responsibilities">
      <dl><div><dt>AI prepares</dt><dd id="sdlc-ai-responsibility"></dd></div><div><dt>People decide</dt><dd id="sdlc-human-responsibility"></dd></div></dl>
      <h4>Artifacts for this handoff</h4><ul id="sdlc-handoff-artifacts"></ul>
    </section>
    <details class="delivery-documentation"><summary>Documentation throughout delivery</summary><p id="sdlc-documentation-policy"></p><ul id="sdlc-documentation-artifacts"></ul><a href="/sdlc?view=documents">Review project documentation and versions</a></details>
    <details class="sdlc-stage-checklist"><summary>Steps in this stage</summary><ol id="sdlc-step-stages" class="sdlc-step-stages"></ol></details><div id="sdlc-step-links" class="sdlc-actions"></div></section>
    <div class="sdlc-sequence-controls"><button type="button" class="secondary" id="sdlc-previous-step">← Previous step</button><button type="button" class="secondary" id="sdlc-current-step">Return to current step</button><button type="button" class="secondary" id="sdlc-next-step">View next step →</button></div>`;
  host.prepend(section);
  const phaseNavigation = document.getElementById("sdlc-phase-tabs");
  document.getElementById("sdlc-navigation").prepend(phaseNavigation);
  phaseNavigation.after(document.getElementById("sdlc-documents-link"));
  const baselinePanel = document.querySelector(".sdlc-source-baseline");
  section
    .querySelector("#sdlc-step-panel")
    .insertBefore(baselinePanel, section.querySelector(".sdlc-stage-checklist"));
  // Reuse the original editor and handlers rather than duplicating requirement inputs.
  const editor = document.getElementById("test-studio");
  const sourceActions = editor.querySelector(".sdlc-requirements-input");
  document.getElementById("generate-form").after(sourceActions);
  const generationControls = editor.querySelector(".controls");
  const generationOptions = document.createElement("section");
  generationOptions.className = "sdlc-generation-options";
  const generationSummary = document.createElement("h4");
  generationSummary.textContent = "Test settings";
  generationOptions.append(generationSummary);
  generationControls.before(generationOptions);
  generationOptions.append(generationControls);
  const missionOptions = document.createElement("section");
  missionOptions.innerHTML = "<h4>AI delivery settings</h4>";
  [...sourceActions.querySelectorAll(":scope > label")].forEach((label) =>
    missionOptions.append(label),
  );
  sourceActions.append(missionOptions);
  const options = document.createElement("details");
  options.id = "requirements-options";
  const optionsSummary = document.createElement("summary");
  optionsSummary.textContent = "Options: business rules, test settings and delivery";
  options.append(optionsSummary);
  generationOptions.before(options);
  options.append(document.getElementById("rule-control"), generationOptions, missionOptions);
  const context = editor.querySelector(".finance-context-settings");
  if (context) options.append(context);
  // Requirements has one source area and one validation action bar.
  editor.classList.add("requirements-simple");
  const actions = document.createElement("div");
  actions.className = "requirements-actions";
  const model = document.getElementById("llm-model").closest("fieldset");
  const buttons = editor.querySelector(".generation-actions");
  buttons.prepend(document.getElementById("validate-requirements"));
  buttons.append(document.getElementById("stop-generation"));
  document.getElementById("stop-generation").disabled = true;
  actions.append(model, buttons);
  document.getElementById("generate-form").append(actions);
  const modelFeedback = document.createElement("div");
  modelFeedback.className = "requirements-model-feedback";
  modelFeedback.append(document.getElementById("llm-model-status"), document.getElementById("refresh-llm-models"));
  actions.after(modelFeedback);
  const validationResult = document.getElementById("requirements-validation-report");
  validationResult.setAttribute("aria-label", "BRD validation outcome");
  // Optional settings remain in the original form and reuse the existing handlers.
  const editorHome = document.createComment("Requirements tool editor location");
  editor.before(editorHome);
  const projectControls = document.querySelector(".sdlc-project-controls");
  const projectStatus = document.getElementById("sdlc-status");
  const workspace = document.querySelector(".sdlc-workspace");
  // Reuse the main-branch visual introduction and live runtime fields.
  const requirementsIntro = document.createElement("div");
  requirementsIntro.className = "requirements-reference-intro";
  requirementsIntro.append(document.querySelector(".finance-hero"), editor.parentElement.querySelector(".workspace-context-bar"));
  workspace.before(requirementsIntro);
  workspace.insertBefore(projectControls, host);
  workspace.insertBefore(projectStatus, host);
  baselinePanel.querySelector("a").remove();
  const editorSlot = document.createElement("div");
  editorSlot.id = "sdlc-requirements-editor";
  baselinePanel.before(editorSlot);
  function placeEditor() {
    if (location.pathname === "/sdlc") {
      const layout = workspace.closest(".sdlc-workflow-layout") || workspace;
      layout.before(requirementsIntro);
    } else editorHome.before(requirementsIntro);
    options.hidden = location.pathname === "/sdlc";
    options.open = location.pathname !== "/sdlc";
    if (location.pathname === "/sdlc") editorSlot.append(editor, validationResult);
    else editorHome.after(editor, validationResult);
  }
  window.addEventListener("workspace-page-changed", placeEditor);
  placeEditor();
  const get = (id) => document.getElementById(id);
  let phases = [],
    definition = [],
    state = null,
    selected = null,
    previousProject = null;
  const label = (value) =>
    value
      .replace(/^Ba /, "Business analyst ")
      .replace(/^Qa /, "QA ")
      .replace(/^Ci /, "CI ")
      .replace(/^Uat$/, "User acceptance testing (UAT)");
  function requestedPhase() {
    const params = new URLSearchParams(location.search);
    if (phases.some((phase) => phase.id === params.get("phase"))) return params.get("phase");
    const stage = params.get("stage");
    return phases.find((phase) => phase.agent_stages.includes(stage))?.id;
  }
  function select(identifier, { navigate = false, focus = false } = {}) {
    if (!phases.some((phase) => phase.id === identifier)) return;
    if (selected === identifier && navigate) return;
    if (
      selected !== identifier &&
      !window.dispatchEvent(new CustomEvent("sdlc-phase-changing", { cancelable: true }))
    )
      return;
    const changed = selected !== identifier;
    selected = identifier;
    if (changed && !new URLSearchParams(location.search).has("stage"))
      document.querySelector(".sdlc-artifact-ledger").open = false;
    if (navigate) window.navigateWorkspace(`/sdlc?phase=${encodeURIComponent(identifier)}`, false);
    render();
    if (focus) get(`sdlc-phase-${identifier}`).focus();
  }
  function render() {
    if (!phases.length) return;
    const phase =
      phases.find((item) => item.id === selected) ||
      phases.find((item) => item.id === state?.phase) ||
      phases[0];
    selected = phase.id;
    get("sdlc-step-panel").dataset.phase = phase.id;
    const documentsView = new URLSearchParams(location.search).get("view") === "documents";
    const pipelineView = new URLSearchParams(location.search).get("view") === "pipeline";
    const pipelineOverview = pipelineView && !new URLSearchParams(location.search).has("phase");
    document.body.dataset.sdlcPhase = documentsView ? "documents" : pipelineView ? "pipeline" : phase.id;
    const legacyStage = new URLSearchParams(location.search).has("stage");
    if (location.pathname === "/sdlc" && !legacyStage && !documentsView) {
      document.querySelector(".topbar h1").textContent = phase.label;
      document.title = `${phase.label} — Auto Finance Quality`;
      document.querySelectorAll("#sdlc-navigation a[aria-current]").forEach((link) => {
        link.removeAttribute("aria-current");
        link.classList.remove("active");
      });
    }
    const index = phases.indexOf(phase),
      activeIndex = phases.findIndex((item) => item.id === state?.phase);
    get("sdlc-sequence-position").hidden = true;
    get("sdlc-step-view-note").hidden = !state;
    get("sdlc-sequence-position").textContent = state
      ? `Current step ${activeIndex + 1} of ${phases.length} · ${phases[activeIndex].label}`
      : "Select or create a project above to begin";
    const tabs = get("sdlc-phase-tabs");
    tabs.replaceChildren();
    phases.forEach((item, position) => {
      const button = document.createElement("a");
      button.href = `/sdlc?phase=${encodeURIComponent(item.id)}`;
      button.className = "nav-item";
      button.id = `sdlc-phase-${item.id}`;
      button.setAttribute("aria-controls", "sdlc-step-panel");
      const isActive = location.pathname === "/sdlc" && !legacyStage && !documentsView && !pipelineOverview && item.id === phase.id;
      button.classList.toggle("active", isActive);
      if (isActive) button.setAttribute("aria-current", "page");
      const number = document.createElement("span");
      number.className = "sdlc-step-number";
      number.textContent = String(position + 1).padStart(2, "0");
      const copy = document.createElement("span"),
        title = document.createElement("strong"),
        status = document.createElement("small");
      title.textContent = item.label;
      status.textContent = !state
        ? (item.id === phase.id ? "Start here" : "")
        : position === activeIndex
          ? "Current step"
          : position < activeIndex
            ? "Earlier step"
            : "Upcoming";
      if (position === activeIndex) button.dataset.currentStage = "true";
      copy.append(title, status);
      button.append(number, copy);
      // Normal links preserve browser history, modified clicks and mobile navigation.
      button.onkeydown = (event) => {
        const movement = { ArrowRight: 1, ArrowLeft: -1 };
        if (event.key in movement) {
          event.preventDefault();
          get(`sdlc-phase-${phases[(position + movement[event.key] + phases.length) % phases.length].id}`).focus();
        }
        if (event.key === "Home") {
          event.preventDefault();
          get(`sdlc-phase-${phases[0].id}`).focus();
        }
        if (event.key === "End") {
          event.preventDefault();
          get(`sdlc-phase-${phases.at(-1).id}`).focus();
        }
      };
      tabs.append(button);
      if (item.id === "business-approval" && isActive && window.baReviewNavigation?.eligible(state)) {
        const children = document.createElement("nav");
        children.id = "ba-review-navigation";
        children.className = "ba-review-navigation";
        children.setAttribute("aria-label", "BA review sections");
        for (const child of window.baReviewNavigation.available(state)) {
          const link = document.createElement("a");
          link.href = window.baReviewNavigation.href(child.id);
          link.textContent = child.label;
          link.dataset.baSection = child.id;
          if (child.id === window.baReviewNavigation.selected(state)) link.setAttribute("aria-current", "page");
          children.append(link);
        }
        tabs.append(children);
      }
    });
    get("sdlc-step-panel").setAttribute("aria-labelledby", `sdlc-phase-${phase.id}`);
    get("sdlc-step-number").textContent = `Step ${index + 1} of ${phases.length}`;
    get("sdlc-step-heading").textContent = phase.label;
    const responsibilityBanner = get("sdlc-responsibilities");
    if (responsibilityBanner.matches(":popover-open")) responsibilityBanner.hidePopover();
    get("requirements-info").hidden = phase.id !== "requirements";
    if (phase.id === "requirements") responsibilityBanner.setAttribute("popover", "auto");
    else responsibilityBanner.removeAttribute("popover");
    get("sdlc-step-description").textContent = phase.description;
    const responsibilities = phase.responsibilities || {};
    get("sdlc-ai-responsibility").textContent = responsibilities.ai || "AI prepares drafts for review.";
    get("sdlc-human-responsibility").textContent = responsibilities.human || "The accountable owner validates the handoff.";
    const renderArtifacts = (id, artifacts) => get(id).replaceChildren(...(artifacts || []).map((text) => {
      const item = document.createElement("li");
      item.textContent = text;
      return item;
    }));
    renderArtifacts("sdlc-handoff-artifacts", responsibilities.artifacts);
    get("sdlc-documentation-policy").closest(".delivery-documentation").hidden = phase.id === "requirements";
    get("sdlc-documentation-policy").textContent = [phase.documentation?.ai, phase.documentation?.human].filter(Boolean).join(" ");
    renderArtifacts("sdlc-documentation-artifacts", phase.documentation?.artifacts);
    get("sdlc-step-view-note").textContent = !state
      ? "Select or create a project above, then add your BRD or requirements below."
      : phase.id === state.phase
        ? "Complete the current stage below to make the next handoff."
        : `Reviewing ${phase.label}. Active work remains in ${phases[activeIndex].label}; return to the current step to record evidence or a decision.`;
    const stages = get("sdlc-step-stages");
    stages.replaceChildren();
    const byId = new Map(definition.map((item) => [item.id, item]));
    const direct = new Set();
    let cursor = phase.stages[0];
    while (phase.stages.includes(cursor) && !direct.has(cursor)) {
      direct.add(cursor);
      cursor = byId.get(cursor)?.next;
    }
    for (const id of phase.stages) {
      const item = byId.get(id);
      if (!item) continue;
      const li = document.createElement("li");
      li.textContent = `${label(item.label)}${!direct.has(id) ? " · Rework path" : ""}`;
      if (id === state?.stage) li.setAttribute("aria-current", "step");
      stages.append(li);
    }
    baselinePanel.hidden = phase.id !== phases[0].id;
    editorSlot.hidden = baselinePanel.hidden;
    const links = get("sdlc-step-links");
    links.replaceChildren();
    for (const destination of phase.id === "business-approval" ? [] : phase.links) {
      if (!baselinePanel.hidden && destination.href === "/?view=requirements") continue;
      if (window.roleCanNavigate && !window.roleCanNavigate(destination.href)) continue;
      const link = document.createElement("a");
      link.className = "button secondary";
      link.href = destination.href;
      link.textContent = destination.label;
      links.append(link);
    }
    get("sdlc-previous-step").disabled = index === 0;
    get("sdlc-next-step").disabled = index === phases.length - 1;
    get("sdlc-current-step").hidden = !state || phase.id === state.phase;
    window.dispatchEvent(
      new CustomEvent("sdlc-phase-selected", {
        detail: { phase, current: phase.id === state?.phase },
      }),
    );
  }
  get("sdlc-previous-step").onclick = () =>
    select(phases[phases.findIndex((item) => item.id === selected) - 1]?.id, { navigate: true });
  get("sdlc-next-step").onclick = () =>
    select(phases[phases.findIndex((item) => item.id === selected) + 1]?.id, { navigate: true });
  get("sdlc-current-step").onclick = () => select(state?.phase, { navigate: true });
  window.addEventListener("sdlc-lifecycle-loaded", (event) => {
    const data = event.detail;
    const changedProject = previousProject !== data?.project.id;
    const oldPhase = state?.phase;
    previousProject = data?.project.id || null;
    state = data?.state || null;
    if (state) {
      phases = state.phases || [];
      definition = state.definition;
    }
    const desired = changedProject
      ? requestedPhase() || state?.phase
      : oldPhase !== state?.phase
        ? state?.phase
        : requestedPhase() || selected || state?.phase;
    // Server handoffs and project switches always reveal the authoritative current work.
    selected = desired || phases[0]?.id;
    if (!changedProject && oldPhase && oldPhase !== state?.phase && location.pathname === "/sdlc") {
      const view = new URLSearchParams(location.search).get("view");
      if (view !== "pipeline" || new URLSearchParams(location.search).has("phase"))
        history.replaceState(null, "", `/sdlc?phase=${encodeURIComponent(selected)}${view === "pipeline" ? "&view=pipeline" : ""}`);
    }
    render();
  });
  window.addEventListener("workspace-page-changed", (event) => {
    if (event.detail.path === "/sdlc") select(requestedPhase() || state?.phase || phases[0]?.id);
  });
  window.addEventListener("sdlc-policy-loaded", (event) => {
    if (!state && Array.isArray(event.detail?.phases)) {
      phases = event.detail.phases;
      definition = event.detail.definition;
      selected = requestedPhase() || selected || phases[0]?.id;
      render();
    }
  });
  document.addEventListener(
    "click",
    (event) => {
      const link = event.target.closest("a[href]");
      if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target)
        return;
      const target = new URL(link.href);
      if (
        target.origin === location.origin &&
        target.pathname === "/sdlc" &&
        !window.dispatchEvent(new CustomEvent("sdlc-phase-changing", { cancelable: true }))
      ) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true,
  );
  window.addEventListener("workspace-role-ready", render);
})();
