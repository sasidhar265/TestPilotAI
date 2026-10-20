/* Source-bound BA proposals and human decisions; all mutations go through project APIs. */
(() => {
  const root = document.createElement("section");
  root.id = "ba-inline-workspace";
  root.className = "ba-inline-workspace";
  root.setAttribute("aria-label", "Review AI suggestions and record BA feedback");
  const initial = window.projectLifecycleSnapshot?.();
  let project = initial?.project || window.sdlcCurrentProject?.(), state = initial?.state;
  let run = null, history = [], selectedRequirement = null, selectedFinding = null;
  let role = document.body.dataset.role || "", busy = false, message = "", loaded = false;
  let poll = null, epoch = 0, draft = "", comment = "";
  let signoffComment = "", startingAnalysis = false, loadError = "";
  const rowComments = new Map();
  const expandedSuggestions = new Set();
  const filters = { severity: "", product: "", category: "", status: "", requirement: "" };
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text != null) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const statusLabel = (value) => ({ PENDING: "Needs review", ACCEPTED_DRAFT: "Accepted as draft", EDITED_DRAFT: "Edited draft", REJECTED: "Declined", CLARIFICATION_REQUESTED: "Awaiting clarification", RESOLVED: "Resolved" }[value] || value.replaceAll("_", " ").toLowerCase());
  const decided = (item) => ["ACCEPTED_DRAFT", "EDITED_DRAFT", "REJECTED", "RESOLVED"].includes(item.review_status);
  const writable = () => ["ba", "admin", "test_lead"].includes(role);
  const active = () => ["queued", "running"].includes(run?.status);
  const button = (label, handler, disabled = false, className = "secondary") => {
    const control = node("button", label, className);
    control.type = "button";
    control.disabled = disabled;
    control.onclick = handler;
    return control;
  };
  const analysisStatus = node("section", null, "ba-analysis-progress");
  analysisStatus.id = "ba-analysis-progress";
  analysisStatus.setAttribute("aria-labelledby", "ba-analysis-heading");
  function renderAnalysisStatus() {
    analysisStatus.replaceChildren();
    const current = run?.project === project?.id && run?.baseline === state?.baseline ? run : null;
    let phase = !loaded ? "loading" : current?.status || "idle";
    if (!state?.approval_context?.source) phase = "missing";
    if (startingAnalysis) phase = "starting";
    if (loadError) phase = "unavailable";
    const labels = { loading: "Loading analysis status", missing: "BRD required", idle: "Not started", starting: "Submitting analysis", queued: "Queued", running: "Analysing BRD", completed: "Ready for BA review", failed: "Analysis failed", cancelled: "Analysis stopped", unavailable: "Status unavailable" };
    analysisStatus.dataset.status = phase;
    const heading = node("h3", "AI analysis progress"); heading.id = "ba-analysis-heading";
    const status = node("p", labels[phase] || "Checking analysis status", "ba-analysis-state");
    status.setAttribute("role", "status"); status.setAttribute("aria-atomic", "true");
    const descriptions = {
      loading: "Checking for an existing AI review of this BRD.",
      missing: "Save the validated BRD in Requirements to make it available for AI review.",
      idle: "Open AI suggestions to start the detailed review for BA decisions. The earlier Requirements assessment remains available as reference.",
      starting: "Submitting the current saved BRD for analysis. Wait for the request to be confirmed.",
      completed: "Read the findings in AI suggestions, record your decisions, then complete Your decision. AI analysis does not grant sign-off.",
    };
    analysisStatus.append(heading, node("p", "AI suggestions for BA review", "ba-analysis-updated"), status, node("p", loadError || descriptions[phase] || current?.progress || "Refresh the review to check its latest status."));
    if (loadError && current) analysisStatus.append(node("p", `Last reported: ${labels[current.status] || current.status}. Current progress could not be verified.`));
    if (["starting", "queued", "running"].includes(phase)) {
      const progress = node("div", null, "ba-analysis-indeterminate");
      progress.setAttribute("role", "progressbar"); progress.setAttribute("aria-label", "AI analysis in progress");
      progress.append(node("span")); analysisStatus.append(progress);
      analysisStatus.append(node("p", "Status updates automatically. Keep reviewing the saved BRD while AI works."));
    }
    if (current?.updated_at) {
      const meta = node("p", `BRD v${current.baseline} · Last update: `, "ba-analysis-updated");
      const time = node("time", new Date(current.updated_at).toLocaleString());
      time.dateTime = current.updated_at; meta.append(time); analysisStatus.append(meta);
    }
    const actions = node("div", null, "sdlc-actions");
    if (["idle", "completed", "failed", "cancelled"].includes(phase)) {
      const link = node("a", phase === "completed" ? "Review AI findings" : "Open AI suggestions", "button secondary");
      link.href = "/sdlc?phase=business-approval&review=suggestions"; actions.append(link);
    }
    if (loadError) actions.append(button("Retry status check", load, busy));
    if (actions.childElementCount) analysisStatus.append(actions);
  }
  window.mountBAAnalysisStatus = host => { host.append(analysisStatus); renderAnalysisStatus(); };
  async function api(path = "", body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 25000);
    try {
      const response = await fetch(`/api/sdlc/projects/${encodeURIComponent(project.id)}/ba-reviews${path}`, {
        method: body ? "POST" : "GET", headers: { "Content-Type": "application/json" },
        ...(body ? { body: JSON.stringify(body) } : {}), signal: controller.signal,
      });
      if (response.status === 401 || response.redirected) throw new Error("Your session expired. Sign in again before reviewing.");
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "The review could not be saved. Reload and retry.");
      return data;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("Review request timed out. Reload to check the saved state before retrying.");
      throw error;
    } finally { clearTimeout(timer); }
  }
  const refreshLifecycle = () => {
    window.dispatchEvent(new Event("requirements-assessment-updated"));
    window.dispatchEvent(new Event("lifecycle-updated"));
  };
  async function load() {
    if (!project) return;
    const version = epoch;
    try {
      const data = await api();
      if (version !== epoch) return;
      const completed = data.run?.status === "completed" && (run?.id !== data.run.id || run?.status !== "completed");
      run = data.run; history = data.history || []; loaded = true; loadError = "";
      if (completed) refreshLifecycle();
      window.dispatchEvent(new Event("ba-review-updated"));
      render(); schedule();
    } catch (error) {
      if (version !== epoch) return;
      loadError = error.message; message = error.message; loaded = true; render(); schedule();
    }
  }
  function schedule() {
    clearTimeout(poll);
    if (active() && !root.hidden && document.body.dataset.sdlcPhase === "business-approval")
      poll = setTimeout(load, 2500);
  }
  async function mutate(path, payload, success) {
    if (busy) return;
    const version = epoch;
    busy = true; message = "Saving…"; render();
    try {
      const result = await api(path, payload);
      if (version !== epoch) return;
      run = result.run || result; message = success;
      if (result.source) {
        window.dispatchEvent(new CustomEvent("ba-brd-revised", { detail: result.source }));
        await window.sdlcRefreshProject?.();
      }
      window.dispatchEvent(new Event("ba-review-updated"));
      comment = ""; draft = "";
      refreshLifecycle();
    } catch (error) { if (version === epoch) message = error.message; }
    finally { if (version === epoch) { busy = false; render(); schedule(); } }
  }
  async function start(force = false, requirement_id = null) {
    if (busy || active()) return;
    startingAnalysis = true; loadError = "";
    try { await mutate("", { baseline: state.baseline, force, requirement_id }, "BA analysis requested. Findings require human review."); }
    finally { startingAnalysis = false; renderAnalysisStatus(); }
  }
  function selectFinding(finding) {
    expandedSuggestions.add(`${run.id}:${finding.finding_id}`);
    selectedFinding = finding.finding_id;
    selectedRequirement = finding.requirement_ids[0];
    draft = finding.human_proposed_text || finding.suggested_requirement_text || "";
    comment = rowComments.get(`${run.id}:${finding.finding_id}`) || "";
    render();
  }
  function sourceView(reference) {
    const target = root.querySelector("#ba-original-source");
    if (!target) return;
    if (reference.source_id === "BRD") {
      const section = run.sections.find((item) => item.id === reference.section_id);
      target.textContent = section ? `${section.id} · extracted text location\n\n${section.text}` : "Source location unavailable. Reload the baseline.";
    } else {
      const source = run.knowledge_sources.find((item) => item.id === reference.source_id);
      target.textContent = source ? `${source.title} · v${source.version} · ${source.authority}\n\n${source.content}` : "Knowledge source unavailable.";
    }
    target.focus(); target.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
  async function requestRework() {
    if (busy || !signoffComment.trim()) { message = "Enter your overall BA comment before requesting changes."; render(); return; }
    if (!state?.can_act || !["requirements", "business-approval"].includes(state.phase)) return;
    const version = epoch;
    busy = true; message = "Saving your rework request…"; render();
    try {
      const response = await fetch(`/api/sdlc/projects/${encodeURIComponent(project.id)}/transitions`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ revision: state.revision, decision: "changes_requested", comment: signoffComment }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Your rework request could not be saved.");
      if (version !== epoch) return;
      message = "Changes requested. Revise the BRD in Requirements, validate it, then return for a new AI review.";
      refreshLifecycle();
    } catch (error) { if (version === epoch) message = error.message; }
    finally { if (version === epoch) { busy = false; render(); } }
  }
  function mountBASignoff(parent) {
    parent.querySelector(".ba-signoff")?.remove();
    if (!writable() || state?.stage === "stakeholder_approval" || !["requirements", "business-approval"].includes(state?.phase)) return;
    const currentReview = run?.baseline === state?.baseline && run?.project === project?.id;
    const signed = currentReview && run?.signoff && state?.backlog_drafting?.signed_off;
    const signoff = node("section", null, "ba-signoff");
    signoff.append(node("h4", signed ? "BA review completed" : "Your overall BA decision"));
    if (signed) {
      signoff.append(node("p", `Signed off by ${run.signoff.actor} · ${run.signoff.created_at} · BRD v${run.signoff.baseline}.`),
        node("p", run.signoff.comment), node("p", "You can now create user-story drafts in Backlog. Business approval remains a separate stakeholder decision."));
    } else {
      const label = node("label", "Overall BA comment");
      const input = node("textarea"); input.rows = 4; input.id = "ba-signoff-comment";
      input.maxLength = 4000; input.value = signoffComment;
      input.placeholder = "Summarise your review, confirm the expected business outcomes, or explain the changes needed.";
      input.oninput = () => { signoffComment = input.value; };
      input.disabled = busy;
      label.append(input); signoff.append(label);
      const actions = node("div", null, "sdlc-actions");
      actions.append(button("Sign off for story drafting", () => {
        if (!signoffComment.trim()) { message = "Enter your overall BA comment before signing off."; render(); return; }
        mutate(`/${run.id}/signoff`, { revision: run.revision, comment: signoffComment }, "BA sign-off saved. Open Backlog to create user-story drafts.");
      }, !currentReview || run?.status !== "completed" || !run?.output || busy || active(), "primary"));
      actions.append(button("Request changes", requestRework, busy || active() || !state.can_act ||
        !state.definition.find((item) => item.id === state.stage)?.reject_to));
      signoff.append(actions, node("p", currentReview && run?.output
        ? "Sign-off checks that all findings are resolved or rejected and no blocking business decisions remain. Accepted or edited proposals are drafts until addressed."
        : "Generate AI suggestions and complete the review before signing off. You can request BRD changes with your comment."));
    }
    if (message) { const status = node("p", message); status.setAttribute("role", "status"); signoff.append(status); }
    const next = parent.querySelector(".ba-workflow-evidence, .ba-business-routing, .ba-backlog-handoff");
    parent.insertBefore(signoff, next);
  }
  window.mountBASignoff = mountBASignoff;
  function appendBRDRevision() {
    const source = state?.approval_context?.source;
    if (!source) return;
    const current = run?.project === project?.id && run?.baseline === state?.baseline;
    if (!source.content?.ba_revision && !run?.output) return;
    const section = node("section", null, "ba-updated-brd"); section.id = "ba-updated-brd";
    section.append(node("h4", "Updated BRD and revalidation"));
    if (source.content?.ba_revision) {
      section.append(node("p", `Updated BRD v${source.version} is saved. The original and earlier decisions remain in project history.`));
      const link = node("a", "Download updated BRD", "button secondary");
      link.href = `/api/sdlc/projects/${encodeURIComponent(project.id)}/ba-documents?document=brd`;
      link.setAttribute("download", ""); section.append(link);
      if (current && run.revalidation?.status === "completed")
        section.append(node("p", `Updated BRD reassessed. Source alignment: ${run.revalidation.alignment_status}. Review the fresh AI findings before sign-off.`));
      if (source.content.ba_revision.pending_feedback?.length)
        section.append(node("p", "Open change requests remain questions, not approved rules. Resolve them in Requirements before signing off."));
    }
    if (current && run.output) {
      const pending = run.output.findings.filter(item => item.review_status === "PENDING").length;
      section.append(node("p", pending ? `${pending} suggestions still need a decision before creating the updated BRD.`
        : "Create a new version using accepted wording. Declined suggestions stay out; unanswered feedback requests remain open questions. Revalidation starts automatically."));
      section.append(button("Create updated BRD & revalidate", () => mutate(`/${run.id}/revised-brd`,
        { revision: run.revision }, "Updated BRD saved. Revalidation and a fresh AI review have started."),
        !writable() || busy || active() || pending > 0 || !run.output.findings.length, "primary"));
    }
    root.append(section);
  }
  function render() {
    // Preserve live drafts when asynchronous review/status updates redraw the workspace.
    root.querySelectorAll("textarea[data-ba-reason-key]").forEach(input => {
      if (input.dataset.reviewId === run?.id) rowComments.set(input.dataset.baReasonKey, input.value);
    });
    renderAnalysisStatus();
    root.replaceChildren();
    const toolbar = node("div", null, "sdlc-actions");
    const missingSource = !state?.approval_context?.source;
    toolbar.append(button(active() ? "AI analysis in progress…" : run ? "Refresh AI suggestions" : "Generate AI suggestions", () => start(Boolean(run)),
      busy || active() || !writable() || missingSource, "primary"));
    toolbar.append(button("Refresh review", load, busy));
    if (active()) toolbar.append(button("Cancel analysis", () => mutate(`/${run.id}/cancel`, {}, "Cancellation recorded."), busy || !writable()));
    root.append(toolbar);
    const status = node("p", message || run?.progress || (loaded ? "Ready to review the saved BRD." : "Loading saved BA reviews…"));
    status.id = "ba-inline-status"; status.setAttribute("role", "status"); root.append(status);
    if (missingSource) { root.append(node("p", "Return to Requirements and save the validated BRD before starting BA review.")); return; }
    if (history.some((item) => item.baseline !== state.baseline))
      root.append(node("p", "The BRD changed. Earlier review decisions and sign-offs remain in history and do not approve this version."));
    if (!run) { appendBRDRevision(); return; }
    const metadata = node("details", null, "ba-review-metadata");
    metadata.append(node("summary", `BRD v${run.baseline} · Review details`), node("p", `Review ${run.id} · ${run.status} · ${run.provider}`));
    root.append(metadata);
    if (!run.output) { appendBRDRevision(); return; }
    const output = run.output;
    const overview = node("div", null, "ba-review-overview");
    const pending = output.findings.filter((item) => !decided(item)).length;
    overview.append(node("h4", "Review suggestions against your BRD"),
      node("p", "Choose a suggestion, check the linked BRD text, then record your decision. Your decisions are saved for BA sign-off."),
      node("p", "Accepting or editing saves a draft proposal. Complete BA sign-off under Your decision when the review is ready."));
    const stats = node("dl", null, "ba-review-stats");
    for (const [value, label] of [[output.findings.length, "AI suggestions"], [pending, "Need attention"], [output.findings.length - pending, "Decisions recorded"]]) {
      const stat = node("div"); stat.append(node("dt", label), node("dd", String(value))); stats.append(stat);
    }
    overview.append(stats);
    root.append(overview);
    const limitations = node("details"); limitations.append(node("summary", "Evidence, in-house knowledge and analysis limitations"));
    const knowledge = node("ul");
    (run.knowledge_sources || []).forEach((item) => {
      const row = node("li"); row.append(button(`${item.title} · v${item.version} · ${item.authority}`, () => sourceView({ source_id: item.id })));
      knowledge.append(row);
    });
    limitations.append(node("p", `AI readiness assessment: ${output.readiness_status.replaceAll("_", " ")}. Human review is still required.`), knowledge);
    (output.analysis_limitations || []).forEach((text) => limitations.append(node("p", text)));
    root.append(limitations);
    const filterBar = node("div", null, "ba-review-filters");
    const selectFilter = (key, label, values) => {
      const wrapper = node("label", label);
      const select = node("select"); select.setAttribute("aria-label", label);
      const all = node("option", "All"); all.value = ""; select.append(all);
      [...new Set(values)].sort().forEach((value) => {
        const option = node("option", key === "status" ? statusLabel(value) : value.replaceAll("_", " ")); option.value = value; select.append(option);
      });
      select.value = filters[key]; select.onchange = () => { filters[key] = select.value; render(); };
      wrapper.append(select); filterBar.append(wrapper);
    };
    selectFilter("severity", "Severity", output.findings.map((f) => f.severity));
    selectFilter("product", "Product", output.requirements.flatMap((r) => r.product_scope));
    selectFilter("category", "Finding category", output.findings.map((f) => f.finding_type));
    selectFilter("status", "Review status", output.findings.map((f) => f.review_status));
    selectFilter("requirement", "Requirement", output.requirements.map((r) => r.requirement_id));
    const filterDetails = node("details", null, "ba-review-filter-details");
    const appliedFilters = Object.values(filters).filter(Boolean).length;
    filterDetails.open = appliedFilters > 0;
    filterDetails.append(node("summary", "Filter suggestions"), filterBar);
    if (appliedFilters) filterDetails.append(button("Clear filters", () => { Object.keys(filters).forEach((key) => { filters[key] = ""; }); render(); }));
    root.append(filterDetails);
    const matching = output.findings.filter((f) => {
      const products = output.requirements.filter((r) => f.requirement_ids.includes(r.requirement_id)).flatMap((r) => r.product_scope);
      return (!filters.severity || f.severity === filters.severity) && (!filters.product || products.includes(filters.product)) &&
        (!filters.category || f.finding_type === filters.category) && (!filters.status || f.review_status === filters.status) &&
        (!filters.requirement || f.requirement_ids.includes(filters.requirement));
    });
    const grid = node("div", null, "ba-inline-grid");
    const navigation = node("nav", null, "ba-requirement-list"); navigation.setAttribute("aria-label", "Suggestions and linked BRD requirements");
    const listHeading = node("div", null, "ba-suggestion-list-heading");
    listHeading.append(node("h4", "Suggestions to review"), node("p", `${matching.length} of ${output.findings.length} suggestions shown. Review each row and add a reason to accept or decline it. Open its BRD comparison when you need more detail.`));
    navigation.append(listHeading);
    const suggestionList = node("ol", null, "ba-suggestion-list");
    navigation.append(suggestionList);
    const requirementDetails = node("details"); requirementDetails.append(node("summary", "Browse BRD requirements"));
    const sections = node("details"); sections.append(node("summary", "BRD source sections"));
    run.sections.forEach((section) => sections.append(button(
      `${section.id} · ${section.text.slice(0, 65)}`, () => sourceView({ source_id: "BRD", section_id: section.id }))));
    requirementDetails.append(sections);
    if (!output.requirements.some((r) => r.requirement_id === selectedRequirement)) selectedRequirement = output.requirements[0]?.requirement_id;
    if (!matching.some((item) => item.finding_id === selectedFinding)) {
      selectedFinding = null;
    }
    if (!selectedFinding && matching.length) {
      const first = matching.find((item) => item.requirement_ids.includes(selectedRequirement)) || matching[0];
      selectedFinding = first.finding_id; selectedRequirement = first.requirement_ids[0];
      draft = first.human_proposed_text || first.suggested_requirement_text || "";
    }
    output.requirements.forEach((requirement) => {
      const control = button(requirement.title, () => { selectedRequirement = requirement.requirement_id; filters.requirement = requirement.requirement_id; selectedFinding = null; draft = ""; comment = ""; render(); });
      control.dataset.requirementId = requirement.requirement_id;
      if (requirement.requirement_id === selectedRequirement) control.setAttribute("aria-current", "true");
      requirementDetails.append(control);
    });
    navigation.append(requirementDetails);
    const requirement = output.requirements.find((r) => r.requirement_id === selectedRequirement);
    const centre = node("section", null, "ba-requirement-editor");
    let proposedLabel;
    const finding = output.findings.find((f) => f.finding_id === selectedFinding && f.requirement_ids.includes(selectedRequirement));
    if (requirement) {
      centre.append(node("p", `${requirement.requirement_id} · BRD v${run.baseline}`, "ba-source-location"), node("h4", requirement.title), node("p", `${requirement.category} · ${requirement.product_scope.join(", ") || "Product unknown"}`),
        node("h5", "1. What the BRD says"));
      const source = node("pre", requirement.source_references.filter((r) => r.source_id === "BRD").map((r) => `${r.section_id}\n${run.sections.find((s) => s.id === r.section_id)?.text || r.quote}`).join("\n\n"), "approval-source");
      source.id = "ba-original-source"; source.tabIndex = -1; centre.append(source);
      centre.append(node("h5", "Extracted requirement (draft)"), node("p", requirement.description));
      proposedLabel = node("label", "Proposed wording · separate from the BRD");
      const editor = node("textarea"); editor.id = "ba-proposed-wording"; editor.rows = 7;
      editor.value = draft || finding?.human_proposed_text || finding?.suggested_requirement_text || "";
      editor.disabled = !writable() || !finding || busy || active();
      editor.oninput = () => { draft = editor.value; }; proposedLabel.append(editor);
      centre.append(button("Reanalyse requirement", () => start(true, requirement.requirement_id), !writable() || busy || active()));
      const calculations = output.calculations.filter((c) => c.requirement_id === requirement.requirement_id);
      calculations.forEach((calculation) => {
        const details = node("details"); details.append(node("summary", "Calculation analysis"));
        for (const [key, value] of Object.entries(calculation)) {
          if (["requirement_id", "evidence_references"].includes(key)) continue;
          details.append(node("h5", key.replaceAll("_", " ")), node("p", Array.isArray(value) ? value.join("; ") || "Unknown" : value || "Unknown — stakeholder decision required"));
        }
        centre.append(details);
      });
      output.dependencies.filter((d) => d.source_requirement_id === requirement.requirement_id).forEach((dependency) =>
        centre.append(node("p", `${dependency.relationship}: ${dependency.target_artifact_or_system} · ${dependency.confirmation_status} · ${dependency.rationale}`)));
    }
    const panel = node("section", null, "ba-context-panel"); panel.setAttribute("aria-label", "AI Business Analyst findings");

    if (!matching.length) navigation.append(node("p", output.findings.length ? "No suggestions match. Clear the filters to see other suggestions." : "AI returned no suggestions. Review the analysis limitations and complete your own BRD review before sign-off."));
    let activeRow;
    matching.forEach((item, index) => {
      const tileKey = `${run.id}:${item.finding_id}`;
      const tile = node("details", null, "ba-suggestion-tile");
      tile.open = expandedSuggestions.has(tileKey);
      const control = node("summary", null, "ba-suggestion-item");
      control.onclick = event => {
        event.preventDefault();
        if (expandedSuggestions.has(tileKey)) { expandedSuggestions.delete(tileKey); render(); }
        else selectFinding(item);
      };
      const meta = node("span", null, "ba-suggestion-tags");
      meta.append(node("span", `${item.severity.toLowerCase()} priority`, "ba-suggestion-priority"), node("span", statusLabel(item.review_status), "ba-suggestion-status"));
      const linked = output.requirements.filter((requirement) => item.requirement_ids.includes(requirement.requirement_id));
      const reference = linked.map((requirement) => requirement.title).join("; ") || "Requirement reference unavailable";
      control.append(node("strong", item.title, "ba-suggestion-title"),
        node("span", `Change / clarification requested: ${item.clarification_question || item.recommended_action}`, "ba-suggestion-reference"),
        node("span", tile.open ? "Hide feedback and decisions ▴" : "Give feedback or decide ▾", "ba-suggestion-open"));
      control.dataset.findingId = item.finding_id;
      if (item.finding_id === finding?.finding_id) control.setAttribute("aria-current", "true");
      const row = node("li", null, "ba-suggestion-row");
      tile.append(control); row.append(tile);
      const decision = node("div", null, "ba-suggestion-row-decision");
      decision.append(meta, node("p", `BRD requirement: ${reference}`, "ba-suggestion-reference"), node("h5", "Your decision on this suggestion"));
      const reason = node("label", "Feedback or decision reason (required)");
      const input = node("textarea"); input.rows = 2; input.maxLength = 4000;
      const key = `${run.id}:${item.finding_id}`;
      input.dataset.baReasonKey = key; input.dataset.reviewId = run.id;
      input.id = item.finding_id === finding?.finding_id ? "ba-finding-comment" : `ba-row-comment-${index}`;
      input.value = rowComments.get(key) || (item.finding_id === finding?.finding_id ? comment : "");
      input.placeholder = "Explain why you accept this suggestion or why it should be declined.";
      input.disabled = !writable() || busy || active();
      if (item.finding_id === finding?.finding_id) comment = input.value;
      input.oninput = () => {
        input.setCustomValidity(""); rowComments.set(key, input.value);
        if (item.finding_id === selectedFinding) comment = input.value;
      };
      reason.append(input); decision.append(reason);
      const rowActions = node("div", null, "ba-finding-actions");
      for (const [action, label] of [["clarify", "Request feedback"], ["accept", "Accept suggestion"], ["reject", "Decline suggestion"]]) {
        rowActions.append(button(label, () => {
          if (!input.value.trim()) { input.setCustomValidity("Enter a reason before saving your decision."); input.reportValidity(); return; }
          rowComments.set(key, input.value);
          selectedFinding = item.finding_id; selectedRequirement = item.requirement_ids[0];
          draft = item.human_proposed_text || item.suggested_requirement_text || "";
          mutate(`/${run.id}/decisions`, { revision: run.revision, finding_id: item.finding_id,
            finding_version: item.version, action, comment: input.value, proposed_text: null },
            "Decision saved. The original BRD remains unchanged.");
        }, !writable() || busy || active(), action === "accept" ? "primary" : "secondary"));
      }
      decision.append(rowActions, node("p", "Accept saves a draft proposal. Decline records that this suggestion should not be applied.", "ba-suggestion-reference"));
      tile.append(decision);
      if (item.finding_id === finding?.finding_id) activeRow = tile;
      suggestionList.append(row);
    });
    if (finding) {
      panel.append(node("h5", "2. What AI suggests and why"), node("h4", finding.title),
        node("p", `${finding.severity.toLowerCase()} priority · ${statusLabel(finding.review_status)}`, "ba-review-counts"),
        node("p", finding.detailed_explanation), node("h5", "Why this matters to the business"),
        node("p", finding.business_impact), node("h5", "Question to clarify"), node("p", finding.clarification_question),
        node("p", `Suggested owner: ${finding.suggested_stakeholder || "Unconfirmed"}`),
        node("p", `Evidence: ${finding.evidence_confidence}`), node("p", finding.recommended_action));
      if (finding.decision_origin_review) panel.append(node("p", `Unchanged proposal; prior decision retained from review ${finding.decision_origin_review}. See review history for the reviewer and rationale.`));
      if (proposedLabel) panel.append(proposedLabel, node("p", "Use Edit Suggestion to save revised wording. Accepting a suggestion does not update the uploaded BRD."));
      if (finding.proposed_acceptance_criteria.length) {
        const criteria = node("ul", null, "ba-acceptance-criteria");
        finding.proposed_acceptance_criteria.forEach((criterion) => criteria.append(node("li", criterion)));
        panel.append(node("h5", "How delivery could be checked (draft)"), criteria);
      }
      finding.evidence_references.forEach((reference) => panel.append(button(`View source · ${reference.source_id} ${reference.section_id || ""}`, () => sourceView(reference))));
      const savedDecisions = (run.decisions || []).filter((item) => item.finding_id === finding.finding_id);
      if (savedDecisions.length) {
        const saved = node("details", null, "ba-saved-feedback");
        saved.append(node("summary", `Saved BA feedback (${savedDecisions.length})`));
        [...savedDecisions].reverse().forEach((item) => {
          const entry = node("div"); entry.append(node("p", `${item.actor} · ${item.action} · ${item.created_at}`, "ba-suggestion-meta"), node("p", item.comment)); saved.append(entry);
        }); panel.append(saved);
      }
      const actions = node("div", null, "ba-finding-actions");
      const more = node("details", null, "ba-more-actions"); more.append(node("summary", "Comment or mark resolved"));
      const additionalActions = node("div", null, "ba-finding-actions");
      more.append(node("p", "Add a comment without changing the decision. Mark resolved after the issue has been addressed; sign-off checks still apply."), additionalActions);
      for (const [action, label] of [["edit", "Edit Suggestion"], ["comment", "Add Comment"], ["resolve", "Mark Resolved"]]) {
        const actionGroup = ["comment", "resolve"].includes(action) ? additionalActions : actions;
        actionGroup.append(button(label, () => {
          if (!comment.trim()) { message = "Enter a decision reason or comment before saving."; render(); return; }
          mutate(`/${run.id}/decisions`, { revision: run.revision, finding_id: finding.finding_id,
            finding_version: finding.version, action, comment, proposed_text: action === "edit" ? root.querySelector("#ba-proposed-wording")?.value || draft : null },
          "Decision saved. The original BRD remains unchanged.");
        }, !writable() || busy || active(), action === "accept" ? "primary" : "secondary"));
      }
      panel.append(actions, more);
      const position = matching.findIndex((item) => item.finding_id === finding.finding_id);
      const pager = node("nav", null, "ba-suggestion-pager"); pager.setAttribute("aria-label", "Move between suggestions");
      pager.append(button("Previous suggestion", () => selectFinding(matching[position - 1]), position <= 0 || busy),
        node("span", `Suggestion ${position + 1} of ${matching.length}`),
        button("Next suggestion", () => selectFinding(matching[position + 1]), position >= matching.length - 1 || busy));
      panel.append(pager);
    } else panel.append(node("p", "Select a finding to compare its source, proposal and decision controls."));
    const detail = node("div", null, "ba-review-detail");
    detail.append(centre, panel);
    grid.append(navigation);
    if (activeRow) {
      const comparison = node("details", null, "ba-suggestion-comparison");
      comparison.open = true;
      comparison.append(node("summary", "BRD comparison and more review options"), detail);
      activeRow.append(comparison);
    } else if (requirement) grid.append(detail);
    root.append(grid);
    const decision = document.getElementById("ba-feedback-rework");
    if (decision) mountBASignoff(decision);
    const download = node("a", "Download review decisions and history", "button secondary");
    download.href = `/api/sdlc/projects/${encodeURIComponent(project.id)}/ba-documents?document=history`;
    download.setAttribute("download", "");
    root.append(download);
    appendBRDRevision();
  }
  window.mountInlineBAReview = (host) => {
    host.append(root);
    render();
  };
  window.inlineBAReviewSnapshot = () => run;
  window.loadWorkspaceProfile().then((profile) => { role = profile.role; render(); }).catch(() => {});
  window.addEventListener("sdlc-project-loaded", (event) => {
    const next = event.detail?.project;
    if (next?.id === project?.id) return;
    clearTimeout(poll); epoch++; rowComments.clear(); expandedSuggestions.clear(); project = next; state = null; run = null; history = [];
    loaded = false; busy = false; loadError = ""; startingAnalysis = false; message = ""; draft = ""; comment = ""; signoffComment = ""; render();
  });
  window.addEventListener("sdlc-lifecycle-loaded", (event) => {
    if (event.detail?.project?.id !== project?.id) return;
    const changed = state?.baseline !== event.detail?.state?.baseline;
    if (state && changed) {
      clearTimeout(poll); epoch++; run = null; loaded = false; busy = false; loadError = ""; startingAnalysis = false;
      selectedRequirement = null; selectedFinding = null; rowComments.clear(); expandedSuggestions.clear(); draft = ""; comment = "";
      signoffComment = "";
      Object.keys(filters).forEach((key) => { filters[key] = ""; });
      message = "BRD version changed. Review the current saved source.";
    }
    state = event.detail?.state;
    if ((!loaded || changed) && document.body.dataset.sdlcPhase === "business-approval") load();
  });
  window.addEventListener("sdlc-phase-selected", () => {
    clearTimeout(poll);
    if (document.body.dataset.sdlcPhase === "business-approval") load();
  });
  window.dispatchEvent(new Event("ba-inline-ready"));
  if (project && state && document.body.dataset.sdlcPhase === "business-approval") load();
})();
