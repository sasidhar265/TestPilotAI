/* Sequential SDLC workspace. All stages, groups and destinations come from backend policy. */
(() => {
  const host = document.getElementById("sdlc-content");
  if (!host) return;
  const section = document.createElement("section");
  section.className = "sdlc-sequence";
  section.setAttribute("aria-label", "SDLC workflow navigation");
  section.innerHTML = `<div class="stage-navigation-heading"><div><h2>Your project</h2></div><p id="sdlc-sequence-position" role="status"></p></div>
    <div id="sdlc-phase-tabs" class="stage-tabs" role="tablist" aria-label="SDLC steps"></div>
    <section id="sdlc-step-panel" role="tabpanel" tabindex="0"><span id="sdlc-step-number" class="section-kicker"></span><h3 id="sdlc-step-heading"></h3><p id="sdlc-step-description"></p>
    <p id="sdlc-step-view-note" role="status"></p><details class="sdlc-stage-checklist"><summary>Steps in this stage</summary><ol id="sdlc-step-stages" class="sdlc-step-stages"></ol></details><div id="sdlc-step-links" class="sdlc-actions"></div></section>
    <div class="sdlc-sequence-controls"><button type="button" class="secondary" id="sdlc-previous-step">← Previous step</button><button type="button" class="secondary" id="sdlc-current-step">Return to current step</button><button type="button" class="secondary" id="sdlc-next-step">View next step →</button></div>`;
  host.prepend(section);
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
  generationOptions.before(document.getElementById("ba-review"));
  const missionOptions = document.createElement("section");
  missionOptions.innerHTML = "<h4>AI delivery settings</h4>";
  [...sourceActions.querySelectorAll(":scope > label")].forEach((label) =>
    missionOptions.append(label),
  );
  sourceActions.querySelector(".sdlc-actions").before(missionOptions);
  const options = document.createElement("details");
  options.id = "requirements-options";
  const optionsSummary = document.createElement("summary");
  optionsSummary.textContent = "Options: business rules, test settings and delivery";
  options.append(optionsSummary);
  generationOptions.before(options);
  options.append(document.getElementById("rule-control"), generationOptions, missionOptions);
  const context = editor.querySelector(".finance-context-settings");
  if (context) options.append(context);
  // Optional settings remain in the original form and reuse the existing handlers.
  const editorHome = document.createComment("Requirements tool editor location");
  editor.before(editorHome);
  const projectControls = document.querySelector(".sdlc-project-controls");
  const projectStatus = document.getElementById("sdlc-status");
  const workspace = document.querySelector(".sdlc-workspace");
  workspace.insertBefore(projectControls, host);
  workspace.insertBefore(projectStatus, host);
  baselinePanel.querySelector("a").remove();
  const editorSlot = document.createElement("div");
  editorSlot.id = "sdlc-requirements-editor";
  baselinePanel.before(editorSlot);
  function placeEditor() {
    options.open = location.pathname !== "/sdlc";
    sourceActions.querySelector('a[href="/sdlc"]').hidden = location.pathname === "/sdlc";
    if (location.pathname === "/sdlc") editorSlot.append(editor);
    else editorHome.after(editor);
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
    const index = phases.indexOf(phase),
      activeIndex = phases.findIndex((item) => item.id === state?.phase);
    get("sdlc-sequence-position").hidden = !state;
    get("sdlc-step-view-note").hidden = !state;
    get("sdlc-sequence-position").textContent = state
      ? `Current step ${activeIndex + 1} of ${phases.length} · ${phases[activeIndex].label}`
      : "Select or create a project above to begin";
    const tabs = get("sdlc-phase-tabs");
    tabs.replaceChildren();
    phases.forEach((item, position) => {
      const button = document.createElement("button");
      button.type = "button";
      button.id = `sdlc-phase-${item.id}`;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-controls", "sdlc-step-panel");
      button.setAttribute("aria-selected", String(item.id === phase.id));
      button.tabIndex = item.id === phase.id ? 0 : -1;
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
      if (position === activeIndex) button.setAttribute("aria-current", "step");
      copy.append(title, status);
      button.append(number, copy);
      button.onclick = () => select(item.id, { navigate: true, focus: true });
      button.onkeydown = (event) => {
        const movement = { ArrowRight: 1, ArrowLeft: -1 };
        if (event.key in movement) {
          event.preventDefault();
          tabs.children[(position + movement[event.key] + phases.length) % phases.length].focus();
        }
        if (event.key === "Home") {
          event.preventDefault();
          tabs.firstElementChild.focus();
        }
        if (event.key === "End") {
          event.preventDefault();
          tabs.lastElementChild.focus();
        }
      };
      tabs.append(button);
    });
    get("sdlc-step-panel").setAttribute("aria-labelledby", `sdlc-phase-${phase.id}`);
    get("sdlc-step-number").textContent = `Step ${index + 1} of ${phases.length}`;
    get("sdlc-step-heading").textContent = phase.label;
    get("sdlc-step-description").textContent = phase.description;
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
    for (const destination of phase.links) {
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
      history.replaceState(null, "", `/sdlc?phase=${encodeURIComponent(selected)}`);
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
