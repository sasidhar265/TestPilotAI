/* Human lifecycle state comes exclusively from the backend workflow policy. */
(() => {
  const host = document.getElementById("sdlc-content");
  if (!host) return;
  const panel = document.createElement("section");
  panel.className = "sdlc-mission";
  panel.id = "project-lifecycle";
  panel.innerHTML = `<h3>Your next action</h3>
    <p id="lifecycle-status" role="status" aria-live="polite">Select a project to see its lifecycle.</p>
    <aside class="lifecycle-next-action" aria-labelledby="lifecycle-next-heading"><h4 id="lifecycle-next-heading">What to do</h4><p id="lifecycle-next-action"></p></aside>
    <p id="lifecycle-impact" role="status"></p>
    <details id="lifecycle-timeline-panel"><summary>View the full workflow and stage requirements</summary><p id="lifecycle-criteria"></p><ol id="lifecycle-timeline" class="sdlc-event-list"></ol></details>
    <div class="lifecycle-action-grid">
    <form id="lifecycle-evidence"><h4>Record evidence</h4>
      <p>Human attestation of an existing artifact or result. References are not independently verified by this form.</p>
      <label>Evidence type<select name="kind" required></select></label>
      <label>Artifact / work item / result reference<input name="reference" required maxlength="2000"></label>
      <label>Outcome<select name="outcome"><option value="passed">Passed</option><option value="failed">Failed</option><option value="blocked">Blocked</option></select></label>
      <label>Evidence notes<textarea name="comment" required maxlength="4000"></textarea></label>
      <button class="primary" type="submit">Record evidence</button></form>
    <form id="lifecycle-decision"><h4>Human decision</h4>
      <label>Decision and actionable feedback<textarea name="comment" required maxlength="4000"></textarea></label>
      <div class="sdlc-actions"><button class="primary" name="decision" value="approved" type="submit">Complete stage</button>
      <button name="decision" value="changes_requested" type="submit" class="secondary">Request rework</button></div></form>
    </div><details><summary>Review evidence and decision history</summary><div id="lifecycle-audit"></div></details>
    <details id="lifecycle-team-panel"><summary>Manage project team</summary><form id="lifecycle-team"><h4>Project team</h4><p>The project owner can add an existing enabled account.</p>
      <label>Account username<input name="username" required maxlength="100"></label><button class="secondary" type="submit">Add team member</button></form></details>`;
  const itemsPanel = document.createElement("details");
  itemsPanel.innerHTML = `<summary id="lifecycle-records-summary">Work for this stage</summary>
    <p>Select an item to review or update it. Create a new item when more work is needed.</p>
    <div class="record-toolbar"><label>Find records<input id="record-search" type="search" placeholder="Title, description or owner"></label><label>Filter records<select id="record-filter"><option value="all">All records</option><option value="mine">Assigned to me</option><option value="impacted">Needs impact review</option><option value="approved">Business approved</option></select></label><button type="button" class="secondary" id="record-new">New record</button></div>
    <div class="record-workbench"><div id="lifecycle-work-items" class="record-list" aria-label="Project records"></div><div class="record-detail">
    <p id="record-context" role="status"></p><label hidden>Edit existing record<select id="lifecycle-item-select"><option value="">New record</option></select></label>
    <form id="lifecycle-item-form">
      <label>Type<select name="kind"><option value="requirement">Requirement</option><option value="epic">Epic</option><option value="story">Story</option><option value="test_case">Test case</option><option value="defect">Defect</option><option value="release">Release</option><option value="documentation">Documentation</option></select></label>
      <label>Title<input name="title" required maxlength="300"></label>
      <label>Description<textarea name="description" maxlength="30000"></textarea></label>
      <label>Work status<select name="status"><option value="draft">Draft</option><option value="ready">Ready</option><option value="active">Active</option><option value="blocked">Blocked</option><option value="resolved">Resolved, awaiting QA</option><option value="done">Done</option></select></label>
      <label>Priority<select name="priority"><option value="medium">Medium</option><option value="critical">Critical</option><option value="high">High</option><option value="low">Low</option></select></label>
      <label>Estimate<input name="estimate" type="number" min="0" max="10000" step="any"></label>
      <label>Assignee username<input name="assignee" maxlength="100" list="record-member-options"><datalist id="record-member-options"></datalist></label>
      <label>Sprint<input name="sprint" maxlength="100"></label>
      <label>Acceptance criteria (one per line)<textarea name="acceptance_criteria"></textarea></label>
      <label>Traceability / dependency links<select name="links" multiple aria-describedby="lifecycle-links-help"></select></label><small id="lifecycle-links-help">Choose existing project records; hold Control or Command to select multiple.</small>
      <label>Supporting links and references (one per line)<textarea name="references"></textarea></label>
      <div class="sdlc-actions"><button class="primary" type="submit">Save changes</button><button class="secondary" type="button" id="lifecycle-clear-draft">Discard draft</button></div>
    </form><section id="record-review" hidden><div class="sdlc-actions"><button class="secondary" id="record-create-defect" type="button" hidden>Create linked defect</button><button class="secondary" id="record-use-evidence" type="button" hidden>Use record as evidence reference</button></div><button class="secondary" id="record-amend" type="button" hidden>Revise requirement</button><h4>Discussion and review</h4><p>Comments are bound to the version reviewed. Approval covers the requirement set through the human decision below.</p><div id="record-comments"></div><form id="record-comment-form"><label>Clarification or review comment<textarea name="comment" required maxlength="4000"></textarea></label><button class="secondary" type="submit">Add comment</button></form><h4>Traceability</h4><div id="record-traceability"></div><details><summary>Version history</summary><div id="record-versions"></div></details><details id="record-ai-panel"><summary>AI assistance · review suggestions</summary><p>Suggestions are drafts from existing versioned agent output. Use in draft, review the result, then save explicitly.</p><div id="record-ai-suggestions"></div><button type="button" class="secondary" id="record-open-agents">Open agent execution tools</button></details></section></div></div><details id="record-trace-matrix"><summary>Project traceability matrix</summary><p>Links show captured source versions; impact flags require review against the current baseline.</p><div class="record-matrix-wrap"><table><thead><tr><th scope="col">Record</th><th scope="col">Sources</th><th scope="col">Used by</th><th scope="col">Impact</th></tr></thead><tbody id="record-matrix-rows"></tbody></table></div></details>`;
  panel.insertBefore(itemsPanel, panel.querySelector(".lifecycle-action-grid"));
  host.prepend(panel);
  const recordOptions = document.createElement("details");
  recordOptions.id = "record-options";
  recordOptions.innerHTML = "<summary>Assignment, planning and links</summary>";
  const recordForm = document.getElementById("lifecycle-item-form");
  recordForm.querySelector(".sdlc-actions").before(recordOptions);
  for (const name of ["priority", "estimate", "assignee", "sprint", "links", "references"])
    recordOptions.append(recordForm.elements[name].closest("label"));
  recordForm.elements.links.closest("label").append(document.getElementById("lifecycle-links-help"));
  let project = null,
    state = null,
    loading = false,
    sequence = 0;
  let items = [],
    currentUsername = "",
    currentRole = "";
  window
    .loadWorkspaceProfile()
    .then((profile) => {
      currentUsername = profile.username || "";
      currentRole = profile.role || (profile.is_admin ? "admin" : "");
    })
    .catch(() => {});
  let visibleKinds = null,
    phaseIsCurrent = true,
    recordDirty = false;
  const get = (id) => document.getElementById(id);
  function setBusy(value) {
    loading = value;
    panel.inert = value;
    panel.setAttribute("aria-busy", String(value));
    get("lifecycle-decision").querySelector('[value="approved"]').disabled =
      value || !state || Boolean(state.missing_evidence.length);
  }
  const message = (text) => {
    get("lifecycle-status").textContent = text;
  };
  async function api(path, payload) {
    const response = await fetch(`/api/sdlc${path}`, {
      method: payload ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      ...(payload ? { body: JSON.stringify(payload) } : {}),
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(
        typeof result.detail === "string" ? result.detail : "Check the required fields.",
      );
    return result;
  }
  async function refresh() {
    const selected = project,
      request = ++sequence;
    if (!selected) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    try {
      const result = await api(`/projects/${selected.id}/lifecycle`);
      if (request !== sequence) return;
      if (!Array.isArray(result.definition)) {
        message("Lifecycle service is unavailable.");
        return;
      }
      state = result;
      get("record-member-options").replaceChildren(
        ...[
          ...new Set([
            selected.owner,
            ...state.audit
              .filter((entry) => entry.action === "member_added")
              .map((entry) => entry.username),
          ]),
        ].map((username) => new Option(username, username)),
      );
      itemsPanel.open = true;
      const current = state.definition.find((item) => item.id === state.stage);
      const readable = (value) =>
        value
          .replaceAll("_", " ")
          .replace(/\bba\b/g, "business analyst")
          .replace(/\bqa\b/g, "QA");
      const stageLabel = current.label
        .replace(/^Ba /, "Business analyst ")
        .replace(/^Qa /, "QA ")
        .replace(/^Ci /, "CI ")
        .replace(/^Uat$/, "User acceptance testing (UAT)");
      get("lifecycle-next-action").textContent = !current.next
        ? "This release is closed. Its records and decision history remain available below."
        : !state.baseline
          ? "Open Requirements, select this project, and save its first requirements version."
          : !state.can_act
            ? `Waiting for the accountable owner (${current.roles.map(readable).join(", ")}). You can review the project records below.`
            : state.missing_evidence.length
              ? `Add the required evidence (${state.missing_evidence.map(readable).join(", ")}), then complete this stage. Request rework if corrections are needed.`
              : state.pending_approval
                ? "Review this stage’s evidence against the saved requirements, then approve it or request corrections with a comment."
                : "The required evidence is recorded. Add a decision comment and complete this stage, or request rework.";
      message(
        `${stageLabel} · Requirements v${state.baseline} · ${!current.next ? "Completed" : state.pending_approval ? "Human approval required" : "Work in progress"} · ${state.can_act ? "Your action queue" : "Owned by " + current.roles.map(readable).join(", ")}`,
      );
      get("lifecycle-criteria").textContent =
        `${current.entry_criteria}. Exit: ${current.evidence.join(", ") || "Accountable human approval"}. Missing evidence: ${state.missing_evidence.join(", ") || "None"}.`;
      get("lifecycle-impact").textContent = state.impacted_evidence.length
        ? `${state.impacted_evidence.length} evidence records relate to older requirements. Review linked stories, tests, approvals and documentation.`
        : "";
      const timeline = get("lifecycle-timeline");
      timeline.replaceChildren();
      for (const item of state.definition) {
        const li = document.createElement("li");
        li.textContent = item.label;
        if (item.id === state.stage) {
          li.setAttribute("aria-current", "step");
          li.style.fontWeight = "bold";
        }
        timeline.append(li);
      }
      const form = get("lifecycle-evidence");
      form.hidden = !state.can_act || !state.baseline || !current.evidence.length;
      form.elements.kind.replaceChildren(
        ...current.evidence.map((kind) => new Option(kind.replaceAll("_", " "), kind)),
      );
      get("lifecycle-decision").hidden = !state.can_act || !state.baseline || !current.next;
      get("lifecycle-decision").querySelector('[value="approved"]').textContent =
        state.pending_approval ? "Approve this version" : "Complete stage";
      get("lifecycle-decision").querySelector('[value="approved"]').disabled =
        loading || Boolean(state.missing_evidence.length);
      get("lifecycle-decision").querySelector('[value="changes_requested"]').hidden =
        !current.reject_to;
      const audit = get("lifecycle-audit");
      audit.replaceChildren();
      for (const item of [...state.evidence, ...state.audit].sort((a, b) =>
        a.created_at.localeCompare(b.created_at),
      )) {
        const p = document.createElement("p");
        p.textContent = `${item.created_at} · ${item.actor} · ${item.action || item.kind} · ${item.decision || item.outcome || ""} · ${item.comment || ""}${item.reference ? " · " + item.reference : ""}`;
        audit.append(p);
      }
      const kindSelect = get("lifecycle-item-form").elements.kind;
      for (const option of kindSelect.options)
        option.disabled =
          !state.work_item_types.includes(option.value) ||
          (currentRole === "developer" && option.value === "story");
      get("lifecycle-item-form").hidden = !state.baseline || !state.work_item_types.length;
      await refreshItems(selected.id);
      window.dispatchEvent(
        new CustomEvent("sdlc-lifecycle-loaded", { detail: { project: selected, state } }),
      );
      const profile = await window.loadWorkspaceProfile();
      if (request === sequence)
        get("lifecycle-team-panel").hidden = profile.username !== selected.owner;
    } catch (error) {
      if (request === sequence) message(error.message);
    }
  }
  let detailSequence = 0,
    detail = null,
    amending = false;
  function editItem() {
    const item = items.find((row) => row.id === get("lifecycle-item-select").value);
    ++detailSequence;
    detail = null;
    get("record-review").hidden = true;
    amending = false;
    const form = get("lifecycle-item-form");
    form.reset();
    const allowed = (state?.work_item_types || []).filter(
      (kind) =>
        (!visibleKinds || visibleKinds.includes(kind)) &&
        !(currentRole === "developer" && kind === "story"),
    );
    for (const option of form.elements.kind.options)
      option.disabled = !allowed.includes(option.value);
    form.hidden = !state?.baseline || (!item && (!phaseIsCurrent || !allowed.length));
    [...form.elements].forEach((element) => {
      element.disabled = false;
    });
    get("record-context").textContent = item
      ? `${item.kind.replaceAll("_", " ")} · v${item.version} · ${item.approved ? "Business approved" : "Not business approved"}${item.impacted ? " · Impact review required" : ""}`
      : "Create a draft record linked to the saved requirements baseline.";
    get("record-new").disabled = !state?.baseline || !phaseIsCurrent || !allowed.length;
    if (allowed.length) form.elements.kind.value = allowed[0];
    recordDirty = false;
    if (item)
      for (const name of [
        "kind",
        "title",
        "description",
        "status",
        "priority",
        "estimate",
        "assignee",
        "sprint",
        "acceptance_criteria",
        "references",
      ]) {
        form.elements[name].value = Array.isArray(item[name])
          ? item[name].join("\n")
          : (item[name] ?? "");
      }
    form.elements.links.replaceChildren(
      ...items
        .filter((row) => row.id !== item?.id)
        .map(
          (row) =>
            new Option(
              `${row.kind}: ${row.title} · v${row.version}${row.impacted ? " · impact review" : ""}`,
              row.id,
              false,
              item?.links.includes(row.id),
            ),
        ),
    );
    form.querySelector('button[type="submit"]').hidden = false;
    configureFields();
    form.elements.kind.disabled = Boolean(item);
    if (item) {
      // Permissions and review actions belong to the loaded version, never the previous row.
      for (const element of form.elements) element.disabled = true;
      loadDetail(item);
    } else {
      for (const option of form.elements.status.options) option.disabled = option.value !== "draft";
      get("record-review").hidden = true;
    }
  }
  function configureFields() {
    const form = get("lifecycle-item-form"),
      kind = form.elements.kind.value;
    for (const field of ["estimate", "sprint"])
      form.elements[field].closest("label").hidden = !["story", "epic"].includes(kind);
    form.elements.assignee.closest("label").hidden = kind === "requirement";
    form.elements.acceptance_criteria.closest("label").hidden = kind === "documentation";
    for (const option of form.elements.links.options) {
      const linked = items.find((row) => row.id === option.value);
      option.disabled = !(state?.item_links?.[kind] || []).includes(linked?.kind);
    }
  }
  get("lifecycle-item-form").elements.kind.addEventListener("change", configureFields);
  async function loadDetail(item) {
    const request = ++detailSequence,
      identifier = project.id;
    get("record-context").textContent += " · Loading review context…";
    try {
      const result = await api(`/projects/${identifier}/work-items/${item.id}/detail`);
      if (
        request !== detailSequence ||
        project?.id !== identifier ||
        get("lifecycle-item-select").value !== item.id
      )
        return;
      detail = result;
      get("record-review").hidden = false;
      get("lifecycle-clear-draft").disabled = false;
      get("lifecycle-item-form").querySelector('button[type="submit"]').disabled = false;
      get("record-create-defect").hidden =
        item.kind !== "test_case" || !phaseIsCurrent || !state.work_item_types.includes("defect");
      get("record-use-evidence").hidden =
        !state.can_act || !phaseIsCurrent || !state.missing_evidence.length;
      get("record-amend").hidden =
        item.kind !== "requirement" || phaseIsCurrent || !result.editable_fields.length;
      const form = get("lifecycle-item-form");
      for (const field of [
        "title",
        "description",
        "status",
        "priority",
        "estimate",
        "assignee",
        "sprint",
        "acceptance_criteria",
        "links",
        "references",
      ])
        form.elements[field].disabled = !result.editable_fields.includes(field) || !phaseIsCurrent;
      form.querySelector('button[type="submit"]').hidden =
        !result.editable_fields.length || !phaseIsCurrent;
      for (const option of form.elements.status.options)
        option.disabled = !result.statuses.includes(option.value);
      for (const option of form.elements.links.options) {
        const linked = items.find((row) => row.id === option.value);
        option.disabled = !result.link_kinds.includes(linked?.kind);
      }
      get("record-context").textContent =
        `${item.kind.replaceAll("_", " ")} · v${item.version} · ${item.approved ? "Business approved" : "Draft / human review required"}${item.impacted ? " · Impact review required" : ""}`;
      renderReview(item, result);
    } catch (error) {
      if (request === detailSequence && project?.id === identifier) {
        get("record-context").textContent = error.message;
        get("lifecycle-clear-draft").disabled = false;
      }
    }
  }
  const node = (tag, text) => {
    const element = document.createElement(tag);
    element.textContent = text;
    return element;
  };
  function renderReview(item, result) {
    get("record-comments").replaceChildren(
      ...result.annotations.map((entry) =>
        node(
          "p",
          `v${entry.base_version} · ${entry.actor} · ${new Date(entry.created_at).toLocaleString()} · ${entry.action.replaceAll("_", " ")}: ${entry.comment}`,
        ),
      ),
    );
    if (!result.annotations.length) get("record-comments").textContent = "No review comments yet.";
    get("record-versions").replaceChildren(
      ...result.versions.map((version) => {
        const entry = document.createElement("details");
        entry.append(
          node(
            "summary",
            `v${version.version} · ${version.author} · ${new Date(version.updated_at).toLocaleString()}`,
          ),
          node("p", version.title),
          node("p", version.description),
          node("p", version.acceptance_criteria.join("\n")),
        );
        return entry;
      }),
    );
    const trace = get("record-traceability");
    trace.replaceChildren();
    const linkedItems = items.filter(
      (row) => item.links.includes(row.id) || row.links.includes(item.id),
    );
    for (const linked of linkedItems) {
      const link = node(
        "button",
        `${item.links.includes(linked.id) ? "Source" : "Used by"}: ${linked.kind.replaceAll("_", " ")} · ${linked.title} · v${linked.version}${linked.impacted ? " · Impacted" : ""}`,
      );
      link.type = "button";
      link.className = "secondary";
      link.onclick = () => openRecord(linked.id);
      trace.append(link);
    }
    for (const reference of item.references) {
      try {
        const url = new URL(reference);
        if (!["https:", "http:"].includes(url.protocol)) throw new Error();
        const link = node("a", reference);
        link.href = url.href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        trace.append(link);
      } catch {
        trace.append(node("p", reference));
      }
    }
    if (!trace.children.length) trace.textContent = "No linked records or external evidence yet.";
    const suggestions = get("record-ai-suggestions");
    suggestions.replaceChildren();
    for (const suggestion of result.suggestions) {
      const card = document.createElement("article");
      card.className = "record-suggestion";
      card.append(
        node("h5", suggestion.title),
        node("p", suggestion.acceptance_criteria.join("\n")),
        node(
          "small",
          `${suggestion.stage} v${suggestion.version} · task ${suggestion.task} · ${suggestion.source_references.join(", ")}`,
        ),
      );
      const decisions = result.annotations.filter(
        (entry) =>
          entry.source?.stage === suggestion.stage &&
          entry.source?.version === suggestion.version &&
          entry.source?.task === suggestion.task &&
          entry.base_version === item.version,
      );
      if (decisions.length)
        card.append(node("p", `Last review: ${decisions.at(-1).action.replaceAll("_", " ")}`));
      for (const [action, label] of [
        ["use_draft", "Use in draft"],
        ["dismiss", "Dismiss suggestion"],
      ]) {
        const button = node("button", label);
        button.className = "secondary";
        button.type = "button";
        button.disabled =
          !result.editable_fields.includes("acceptance_criteria") || !phaseIsCurrent;
        button.onclick = async () => {
          if (recordDirty) {
            message("Save or clear your draft before reviewing another suggestion.");
            return;
          }
          button.disabled = true;
          setBusy(true);
          try {
            await api(`/projects/${project.id}/work-items/${item.id}/annotations`, {
              base_version: item.version,
              action,
              comment:
                action === "use_draft"
                  ? "Copied suggestion into an editable draft; explicit save and human approval remain required."
                  : "Suggestion dismissed by reviewer.",
              source: {
                stage: suggestion.stage,
                version: suggestion.version,
                task: suggestion.task,
              },
            });
            if (action === "use_draft") {
              const form = get("lifecycle-item-form");
              form.elements.acceptance_criteria.value = [
                ...new Set([...item.acceptance_criteria, ...suggestion.acceptance_criteria]),
              ].join("\n");
              form.elements.references.value = [
                ...new Set([
                  ...item.references,
                  `agent-artifact:${suggestion.stage}:v${suggestion.version}:task:${suggestion.task}`,
                ]),
              ].join("\n");
              recordDirty = true;
              message(
                "Suggestion added to your draft. Review it, then choose Save changes.",
              );
            } else await loadDetail(item);
          } catch (error) {
            message(error.message);
          } finally {
            button.disabled = false;
            setBusy(false);
          }
        };
        card.append(button);
      }
      suggestions.append(card);
    }
    if (!result.suggestions.length)
      suggestions.textContent =
        "No current-baseline agent task suggestions. Use the existing agent tools to generate and inspect real outputs.";
  }
  function openRecord(identifier) {
    if (recordDirty || loading) {
      message("Save or clear your draft before opening another record.");
      return false;
    }
    const target = items.find((row) => row.id === identifier);
    if (!target) return false;
    if (visibleKinds && !visibleKinds.includes(target.kind)) {
      const phase = state.phases.find((entry) => entry.record_kinds.includes(target.kind));
      if (phase) window.navigateWorkspace(`/sdlc?phase=${encodeURIComponent(phase.id)}`, false);
    }
    const select = get("lifecycle-item-select");
    if (![...select.options].some((option) => option.value === identifier))
      select.add(new Option(items.find((row) => row.id === identifier).title, identifier));
    select.value = identifier;
    document
      .querySelectorAll(".record-row")
      .forEach((row) =>
        row.setAttribute("aria-pressed", String(row.dataset.recordId === identifier)),
      );
    editItem();
    itemsPanel.open = true;
    return true;
  }
  get("record-create-defect").onclick = () => {
    if (recordDirty) {
      message("Save or clear your draft first.");
      return;
    }
    const source = detail.item;
    get("lifecycle-item-select").value = "";
    editItem();
    const form = get("lifecycle-item-form");
    form.elements.kind.value = "defect";
    configureFields();
    form.elements.title.value = `Defect: ${source.title}`;
    recordOptions.open = true;
    for (const option of form.elements.links.options) option.selected = option.value === source.id;
    recordDirty = true;
    message(
      "Enter the observed failure and real execution reference, then save the linked defect draft.",
    );
  };
  get("record-use-evidence").onclick = () => {
    get("lifecycle-evidence").elements.reference.value =
      `work-item:${detail.item.id}:v${detail.item.version}`;
    get("lifecycle-evidence").scrollIntoView({ block: "center", behavior: "smooth" });
    message(
      "Reference filled. Record the actual outcome and notes before submitting a human attestation.",
    );
  };
  get("record-amend").onclick = () => {
    amending = true;
    const form = get("lifecycle-item-form");
    for (const field of detail.editable_fields) form.elements[field].disabled = false;
    form.querySelector('button[type="submit"]').hidden = false;
    message(
      "Saving this amendment reopens requirements analysis and requires a new human approval. Previous versions remain in history.",
    );
  };
  window.addEventListener("beforeunload", (event) => {
    if (recordDirty || loading) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  window.projectRecordDraftPending = () => recordDirty || loading;
  window.openProjectRecord = openRecord;
  get("record-open-agents").onclick = () => {
    const tools = get("sdlc-agent-tools");
    tools.open = true;
    tools.scrollIntoView({ block: "start", behavior: "smooth" });
  };
  get("record-comment-form").onsubmit = async (event) => {
    event.preventDefault();
    if (!project || !detail || loading || recordDirty) {
      message("Save or clear your record draft before adding a review comment.");
      return;
    }
    const form = event.currentTarget,
      button = form.querySelector("button");
    button.disabled = true;
    try {
      await api(`/projects/${project.id}/work-items/${detail.item.id}/annotations`, {
        base_version: detail.item.version,
        action: "comment",
        comment: form.elements.comment.value,
      });
      form.reset();
      await loadDetail(detail.item);
      message("Review comment saved.");
      window.dispatchEvent(new Event("lifecycle-updated"));
    } catch (error) {
      message(error.message);
    } finally {
      button.disabled = false;
    }
  };
  async function refreshItems(identifier) {
    const rows = await api(`/projects/${identifier}/work-items`);
    if (project?.id !== identifier || !Array.isArray(rows)) return;
    items = rows;
    window.dispatchEvent(new CustomEvent("sdlc-records-loaded", { detail: { items, project } }));
    renderItems();
  }
  function renderItems() {
    const select = get("lifecycle-item-select"),
      selected = select.value;
    select.replaceChildren(
      new Option("New record", ""),
      ...items
        .filter((item) => !visibleKinds || visibleKinds.includes(item.kind))
        .map((item) => new Option(`${item.kind}: ${item.title}`, item.id)),
    );
    select.value = items.some((item) => item.id === selected) ? selected : "";
    const matrix = get("record-matrix-rows");
    matrix.replaceChildren();
    for (const item of items) {
      const row = document.createElement("tr");
      for (const values of [
        [item],
        items.filter((record) => item.links.includes(record.id)),
        items.filter((record) => record.links.includes(item.id)),
      ]) {
        const cell = document.createElement("td");
        for (const linked of values) {
          const button = node(
            "button",
            `${linked.kind.replaceAll("_", " ")}: ${linked.title} · v${linked.version}${item.link_versions[linked.id] ? " · linked v" + item.link_versions[linked.id] : ""}`,
          );
          button.type = "button";
          button.className = "secondary";
          button.onclick = () => openRecord(linked.id);
          cell.append(button);
        }
        if (!values.length) cell.textContent = "None";
        row.append(cell);
      }
      row.append(node("td", item.impacted ? "Review required" : "Current source versions"));
      matrix.append(row);
    }
    const list = get("lifecycle-work-items");
    list.replaceChildren();
    const query = get("record-search").value.trim().toLowerCase(),
      filter = get("record-filter").value;
    const username = currentUsername;
    for (const item of items.filter(
      (row) =>
        (!visibleKinds || visibleKinds.includes(row.kind)) &&
        `${row.title} ${row.description} ${row.assignee}`.toLowerCase().includes(query) &&
        (filter === "all" ||
          (filter === "mine" && row.assignee === username) ||
          (filter === "impacted" && row.impacted) ||
          (filter === "approved" && row.approved)),
    )) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "record-row";
      button.dataset.recordId = item.id;
      button.setAttribute("aria-pressed", String(item.id === selected));
      button.append(
        node("strong", item.title),
        node(
          "small",
          `${item.kind.replaceAll("_", " ")} · ${item.status} · v${item.version}${item.approved ? " · Business approved" : ""}${item.impacted ? " · Impact review" : ""}`,
        ),
      );
      button.onclick = () => openRecord(item.id);
      list.append(button);
    }
    if (!list.children.length)
      list.textContent = "No matching records. Create a record or change the filters.";
    if (!recordDirty && get("record-search") !== document.activeElement) editItem();
  }
  get("record-search").oninput = renderItems;
  get("record-filter").onchange = renderItems;
  get("record-new").onclick = () => {
    if (recordDirty) {
      message("Save or clear your current draft first.");
      return;
    }
    get("lifecycle-item-select").value = "";
    editItem();
  };
  let previousRecord = "";
  get("lifecycle-item-select").addEventListener("focus", () => {
    previousRecord = get("lifecycle-item-select").value;
  });
  get("lifecycle-item-select").onchange = () => {
    if (recordDirty) {
      get("lifecycle-item-select").value = previousRecord;
      message("Save or clear your draft before opening another record.");
      return;
    }
    editItem();
  };
  get("lifecycle-item-form").addEventListener("input", () => {
    recordDirty = true;
  });
  get("lifecycle-item-form").addEventListener("change", () => {
    recordDirty = true;
  });
  get("lifecycle-clear-draft").onclick = () => {
    get("lifecycle-item-select").value = "";
    recordDirty = false;
    editItem();
  };
  window.addEventListener("sdlc-phase-changing", (event) => {
    if (loading || recordDirty) {
      event.preventDefault();
      message(
        loading
          ? "Wait for the current save to finish."
          : "Save or clear your record draft before switching steps.",
      );
    }
  });
  window.addEventListener("sdlc-phase-selected", (event) => {
    get("lifecycle-records-summary").textContent =
      `${event.detail.phase.label}: work items`;
    visibleKinds = event.detail.phase.record_kinds;
    phaseIsCurrent = event.detail.current;
    panel.querySelector(".lifecycle-action-grid").hidden = !phaseIsCurrent;
    panel.querySelector(".lifecycle-next-action").hidden = !phaseIsCurrent;
    renderItems();
  });
  get("lifecycle-item-form").onsubmit = async (event) => {
    event.preventDefault();
    if (loading || !project || !state || (!phaseIsCurrent && !amending)) return;
    setBusy(true);
    const form = event.currentTarget;
    const item = items.find((row) => row.id === get("lifecycle-item-select").value);
    const payload = { ...item, ...Object.fromEntries(new FormData(form)) };
    payload.id = item?.id || null;
    payload.base_version = item?.version || 0;
    payload.estimate =
      payload.estimate == null || payload.estimate === "" ? null : Number(payload.estimate);
    for (const field of ["acceptance_criteria", "references"])
      payload[field] = (Array.isArray(payload[field]) ? payload[field].join("\n") : payload[field])
        .split("\n")
        .map((value) => value.trim())
        .filter(Boolean);
    payload.links = [...form.elements.links.selectedOptions].map((option) => option.value);
    try {
      const saved = await api(`/projects/${project.id}/work-items`, payload);
      recordDirty = false;
      get("lifecycle-item-select").add(new Option(saved.title, saved.id));
      get("lifecycle-item-select").value = saved.id;
      await refresh();
      window.dispatchEvent(new Event("lifecycle-updated"));
    } catch (error) {
      message(error.message);
    } finally {
      setBusy(false);
    }
  };
  for (const [id, suffix] of [
    ["lifecycle-evidence", "evidence"],
    ["lifecycle-decision", "transitions"],
    ["lifecycle-team", "members"],
  ]) {
    get(id).onsubmit = async (event) => {
      event.preventDefault();
      if (loading || !project || !state || (suffix !== "members" && !phaseIsCurrent)) return;
      if (recordDirty) {
        message("Save or clear your record draft before recording another action.");
        return;
      }
      setBusy(true);
      const form = event.currentTarget;
      const payload = Object.fromEntries(new FormData(form));
      if (suffix !== "members") payload.revision = state.revision;
      if (suffix === "transitions") payload.decision = event.submitter.value;
      const selected = project.id;
      try {
        await api(`/projects/${selected}/${suffix}`, payload);
        form.reset();
        if (project?.id === selected) await refresh();
        window.dispatchEvent(new Event("lifecycle-updated"));
      } catch (error) {
        message(error.message);
      } finally {
        setBusy(false);
      }
    };
  }
  window.addEventListener("sdlc-project-loaded", (event) => {
    project = event.detail?.project || null;
    state = null;
    items = [];
    detailSequence++;
    detail = null;
    recordDirty = false;
    visibleKinds = null;
    phaseIsCurrent = true;
    if (!project) window.dispatchEvent(new CustomEvent("sdlc-lifecycle-loaded", { detail: null }));
    refresh();
  });
  window.addEventListener("workspace-role-ready", refresh);
  const dashboard = document.querySelector('[data-workspace-page="/project-dashboard"]');
  if (dashboard) {
    const queue = document.createElement("section");
    queue.className = "panel";
    queue.innerHTML =
      '<h2>Project lifecycle queue</h2><p>Current lifecycle and accountable work across your projects.</p><label>Show projects<select id="lifecycle-queue-filter"><option value="all">All projects</option><option value="action">Needs my action</option><option value="approval">My pending approvals</option><option value="blocked">Missing required evidence</option></select></label><div id="lifecycle-queue" role="status"></div>';
    dashboard.prepend(queue);
    async function refreshQueue() {
      try {
        const rows = await api("/queue"),
          list = get("lifecycle-queue");
        list.replaceChildren();
        const filter = get("lifecycle-queue-filter").value;
        for (const row of rows.filter(
          (row) =>
            filter === "all" ||
            (filter === "action" && row.lifecycle.can_act) ||
            (filter === "approval" && row.lifecycle.can_act && row.lifecycle.pending_approval) ||
            (filter === "blocked" && row.lifecycle.missing_evidence.length),
        )) {
          const p = document.createElement("article"),
            link = document.createElement("a");
          link.href = "/sdlc";
          link.textContent = `${row.project.name} · ${row.lifecycle.stage.replaceAll("_", " ")} · ${row.lifecycle.can_act ? "Your action" : "Awaiting owner"}${row.lifecycle.pending_approval ? " · Approval pending" : ""}`;
          const openProject = async (phase) => {
            try {
              await window.sdlcSelectProject(row.project.id);
              window.navigateWorkspace(phase ? `/sdlc?phase=${phase}` : "/sdlc");
            } catch (error) {
              message(error.message);
            }
          };
          link.onclick = (event) => {
            event.preventDefault();
            event.stopPropagation();
            openProject();
          };
          p.append(link);
          if (row.metrics) {
            const metrics = document.createElement("div");
            metrics.className = "sdlc-actions";
            for (const [key, label, phase] of [
              ["requirements", "Requirements", "requirements"],
              ["approved_requirements", "Approved requirements", "business-approval"],
              ["stories", "Stories", "backlog"],
              ["test_cases", "Test cases", "qa"],
              ["open_defects", "Open defects", "qa"],
              ["documentation", "Documents", row.lifecycle.phase],
            ]) {
              const button = node("button", `${label}: ${row.metrics[key]}`);
              button.type = "button";
              button.className = "secondary";
              button.onclick = () => openProject(phase);
              metrics.append(button);
            }
            p.append(metrics);
          }
          list.append(p);
        }
        if (!list.children.length)
          list.textContent = rows.length
            ? "No projects match this queue filter."
            : "No accessible projects. Create a project in the SDLC workspace or ask its owner to add your account.";
      } catch (error) {
        get("lifecycle-queue").textContent = error.message;
      }
    }
    get("lifecycle-queue-filter").onchange = refreshQueue;
    window.addEventListener("workspace-page-changed", (event) => {
      if (event.detail.path === "/project-dashboard") {
        if (new URLSearchParams(location.search).get("queue") === "approval")
          get("lifecycle-queue-filter").value = "approval";
        refreshQueue();
      }
    });
    window.addEventListener("lifecycle-updated", refreshQueue);
    if (location.pathname === "/project-dashboard") {
      if (new URLSearchParams(location.search).get("queue") === "approval")
        get("lifecycle-queue-filter").value = "approval";
      refreshQueue();
    }
  }
})();
