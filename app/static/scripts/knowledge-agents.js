(() => {
  const $ = (id) => document.getElementById(id);
  let inventory = { agents: [], stages: {}, profile: "" };
  let admin = false;
  let editing = null;
  let reviewing = null;
  let busy = false;
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  async function api(path, method = "GET", body) {
    const response = await fetch(path, {
      method,
      cache: "no-store",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const value = await response.json().catch(() => ({}));
    if (!response.ok)
      throw new Error(
        typeof value.detail === "string"
          ? value.detail
          : "Check the required fields and try again.",
      );
    return value;
  }
  function button(label, action, primary = false) {
    const element = node("button", label, primary ? "button primary" : "button");
    element.type = "button";
    element.addEventListener("click", action);
    return element;
  }
  function describe(item) {
    const definition = item.latest.definition;
    const section = node("div", undefined, "ka-definition-preview");
    section.append(node("h3", definition.name), node("p", definition.purpose));
    for (const [label, value] of [
      ["Topic / category", definition.domain],
      ["Profile", definition.profile],
      ["Stages", definition.stages.map((stage) => inventory.stages[stage]).join(", ")],
      ["Source", definition.source_reference],
      ["Guidance", definition.instructions],
      ["Knowledge", definition.knowledge],
    ]) {
      const block = node("div");
      block.append(node("strong", label), node("p", value));
      section.append(block);
    }
    return section;
  }
  function render() {
    const query = $("ka-search").value.trim().toLowerCase();
    const filter = $("ka-filter").value;
    const agents = inventory.agents.filter((item) => {
      const definition = item.latest.definition;
      return (
        (!query ||
          [definition.name, definition.domain, definition.purpose]
            .join(" ")
            .toLowerCase()
            .includes(query)) &&
        (filter === "all" ||
          (filter === "active" && item.published) ||
          filter === item.latest.status)
      );
    });
    const cards = agents.map((item) => {
      const definition = item.latest.definition;
      const card = node("article", undefined, "ka-card");
      card.id = item.id;
      const heading = node("div", undefined, "ka-card-heading");
      heading.append(
        node("h3", definition.name),
        node(
          "span",
          item.published ? `Published v${item.published.revision}` : "Not published",
          "ka-badge",
        ),
      );
      card.append(
        heading,
        node("p", definition.purpose),
        node("p", `${definition.domain} · Profile: ${definition.profile}`, "ka-help"),
      );
      card.append(
        node(
          "p",
          `Latest: v${item.latest.revision} · ${item.latest.status}${item.published && item.published.revision !== item.latest.revision ? ` · Active guidance remains at v${item.published.revision}` : ""}`,
          "ka-help",
        ),
      );
      if (definition.profile !== inventory.profile)
        card.append(
          node(
            "p",
            "This knowledge entry is scoped to another profile and is not used by the current workspace.",
            "ka-help",
          ),
        );
      const stages = node("div", undefined, "ka-tags");
      stages.append(
        ...definition.stages.map((stage) => node("span", inventory.stages[stage] || stage)),
      );
      card.append(stages);
      const actions = node("div", undefined, "ka-card-actions");
      actions.append(
        button("View / history", () => history(item)),
        button("Export", () => exportAgent(item)),
      );
      if (admin) {
        actions.append(button("Edit draft", () => editor(item)));
        if (item.latest.status === "draft") actions.append(button("Review", () => review(item)));
        if (item.latest.status === "reviewed")
          actions.append(
            button("Publish to app", () => change(item, "publish", item.latest.revision), true),
          );
        if (item.published)
          actions.append(
            button("Withdraw", () => change(item, "withdraw", item.published.revision)),
          );
      }
      card.append(actions);
      return card;
    });
    $("ka-list").replaceChildren(...cards);
    if (!cards.length)
      $("ka-list").append(
        node(
          "div",
          query || filter !== "all"
            ? "No knowledge entries match these filters."
            : "Your knowledge workspace is ready. Add application knowledge to create your first entry.",
          "ka-empty",
        ),
      );
  }
  async function load() {
    $("ka-list").setAttribute("aria-busy", "true");
    $("ka-refresh").disabled = true;
    try {
      inventory = await api("/api/knowledge-agents");
      render();
      $("ka-status").textContent =
        `${inventory.agents.length} knowledge entries · ${inventory.agents.filter((item) => item.published).length} published · Active profile: ${inventory.profile}`;
    } catch (error) {
      $("ka-status").textContent = error.message;
    } finally {
      $("ka-list").setAttribute("aria-busy", "false");
      $("ka-refresh").disabled = false;
    }
  }
  function editor(item = null, imported = null) {
    editing = item;
    const form = $("ka-form");
    form.reset();
    $("ka-editor-status").textContent = "";
    $("ka-editor-title").textContent = item
      ? `Edit ${item.latest.definition.name}`
      : "Add application knowledge";
    const definition = imported ||
      item?.latest.definition || { profile: inventory.profile, stages: [] };
    for (const name of [
      "name",
      "domain",
      "purpose",
      "profile",
      "source_reference",
      "instructions",
      "knowledge",
    ])
      form.elements[name].value = definition[name] || "";
    $("ka-stages").replaceChildren(
      ...Object.entries(inventory.stages).map(([stage, title]) => {
        const label = node("label", undefined, "ka-checkbox");
        const input = node("input");
        input.type = "checkbox";
        input.name = "stages";
        input.value = stage;
        input.checked = definition.stages.includes(stage);
        label.append(input, node("span", title));
        return label;
      }),
    );
    $("ka-editor").showModal();
  }
  function review(item) {
    reviewing = item;
    $("ka-review-form").reset();
    $("ka-review-status").textContent = "";
    $("ka-review-preview").replaceChildren(describe(item));
    $("ka-review").showModal();
  }
  async function change(item, action, revision) {
    if (busy) return;
    busy = true;
    $("ka-status").textContent = "Updating knowledge entry…";
    try {
      await api(`/api/admin/knowledge-agents/${item.id}/${action}`, "POST", { revision });
      await load();
      $("ka-status").textContent =
        `${item.latest.definition.name}: ${action === "publish" ? "published to the application" : action === "rollback" ? "previous published revision activated" : "withdrawn from the workflow"}. Changes apply to new generation requests.`;
    } catch (error) {
      $("ka-status").textContent = error.message;
    } finally {
      busy = false;
    }
  }
  function comparison(revisions, publishedRevision) {
    const section = node("section", undefined, "ka-comparison");
    section.append(node("h3", "Compare versions"));
    if (revisions.length < 2) {
      section.append(node("p", "Save another revision to compare definition changes.", "ka-help"));
      return section;
    }
    const controls = node("div", undefined, "ka-comparison-controls");
    const selects = [];
    for (const title of ["Version A", "Version B"]) {
      const label = node("label", title);
      const select = node("select");
      select.setAttribute("aria-label", title);
      for (const version of revisions)
        select.add(
          new Option(`v${version.revision} · ${version.status}`, String(version.revision)),
        );
      label.append(select);
      controls.append(label);
      selects.push(select);
    }
    selects[0].value = String(
      publishedRevision && publishedRevision !== revisions[0].revision
        ? publishedRevision
        : revisions[1].revision,
    );
    selects[1].value = String(revisions[0].revision);
    const showAll = node("label", undefined, "ka-checkbox");
    const checkbox = node("input");
    checkbox.type = "checkbox";
    showAll.append(checkbox, node("span", "Show unchanged fields"));
    controls.append(showAll);
    const count = node("p", undefined, "ka-comparison-count");
    count.setAttribute("role", "status");
    const fields = node("div", undefined, "ka-comparison-fields");
    function draw() {
      const before = revisions.find(
        (version) => String(version.revision) === selects[0].value,
      ).definition;
      const after = revisions.find(
        (version) => String(version.revision) === selects[1].value,
      ).definition;
      const changed = [];
      const blocks = [];
      for (const [key, title] of [
        ["name", "Title"],
        ["purpose", "Purpose"],
        ["domain", "Topic / category"],
        ["profile", "Profile scope"],
        ["stages", "Workflow stages"],
        ["source_reference", "Source reference"],
        ["instructions", "Usage guidance"],
        ["knowledge", "Knowledge content"],
      ]) {
        const format = (value) =>
          Array.isArray(value)
            ? value.map((stage) => inventory.stages[stage] || stage).join("\n")
            : value;
        const a = format(before[key]),
          b = format(after[key]);
        const differs = a !== b;
        if (differs) changed.push(title);
        if (!differs && !checkbox.checked) continue;
        const block = node("section", undefined, "ka-comparison-field");
        block.append(node("h4", `${title} · ${differs ? "Changed" : "Unchanged"}`));
        const columns = node("div", undefined, "ka-comparison-columns");
        for (const [label, value] of [
          [`Version A · v${selects[0].value}`, a],
          [`Version B · v${selects[1].value}`, b],
        ]) {
          const pane = node(
            "div",
            undefined,
            differs ? "ka-diff-pane ka-diff-changed" : "ka-diff-pane",
          );
          pane.append(node("strong", label), node("p", value));
          columns.append(pane);
        }
        block.append(columns);
        blocks.push(block);
      }
      count.textContent = `${changed.length} definition fields differ. Review notes and publishing events are listed below.`;
      fields.replaceChildren(...blocks);
      if (!blocks.length)
        fields.append(node("p", "No definition changes between these versions.", "ka-help"));
    }
    selects.forEach((select) => select.addEventListener("change", draw));
    checkbox.addEventListener("change", draw);
    section.append(controls, count, fields);
    draw();
    return section;
  }
  async function history(item) {
    $("ka-history-content").replaceChildren(describe(item), node("p", "Loading version history…"));
    $("ka-history").showModal();
    try {
      const data = await api(`/api/knowledge-agents/${item.id}/history`);
      const content = $("ka-history-content");
      content.replaceChildren(comparison(data.revisions, item.published?.revision), describe(item));
      for (const version of data.revisions) {
        const block = node("section", undefined, "ka-version");
        block.append(
          node("h3", `Version ${version.revision} · ${version.status}`),
          node("p", `${version.created_at} · Saved by ${version.created_by}`),
          node("p", version.review_note || "Not reviewed"),
        );
        const source = node("details");
        source.append(node("summary", "Inspect this version"), describe({ latest: version }));
        block.append(source);
        if (
          admin &&
          version.status === "published" &&
          item.published?.revision !== version.revision
        )
          block.append(
            button(`Activate v${version.revision}`, async () => {
              $("ka-history").close();
              await change(item, "rollback", version.revision);
            }),
          );
        content.append(block);
      }
      content.append(node("h3", "Publishing audit"));
      for (const event of data.events)
        content.append(
          node(
            "p",
            `${event.at} · ${event.action.replaceAll("_", " ")} · v${event.revision} · ${event.actor}`,
            "ka-help",
          ),
        );
    } catch (error) {
      $("ka-history-content").append(node("p", error.message));
    }
  }
  async function exportAgent(item) {
    try {
      const value = await api(`/api/knowledge-agents/${item.id}/export`);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
      );
      const link = node("a");
      link.href = url;
      link.download = `knowledge-information-${item.id}.json`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      $("ka-status").textContent = error.message;
    }
  }
  $("ka-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!admin || busy) return;
    const data = new FormData(event.currentTarget);
    const definition = Object.fromEntries(
      ["name", "domain", "purpose", "profile", "source_reference", "instructions", "knowledge"].map(
        (key) => [key, String(data.get(key) || "").trim()],
      ),
    );
    definition.stages = data.getAll("stages");
    if (!definition.stages.length) {
      $("ka-editor-status").textContent = "Select at least one workflow stage.";
      return;
    }
    busy = true;
    const submit = event.currentTarget.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      await api(
        editing ? `/api/admin/knowledge-agents/${editing.id}` : "/api/admin/knowledge-agents",
        editing ? "PUT" : "POST",
        editing ? { ...definition, expected_revision: editing.latest.revision } : definition,
      );
      $("ka-editor").close();
      await load();
    } catch (error) {
      $("ka-editor-status").textContent = error.message;
    } finally {
      busy = false;
      submit.disabled = false;
    }
  });
  $("ka-review-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!admin || busy) return;
    busy = true;
    const submit = event.currentTarget.querySelector('[type="submit"]');
    submit.disabled = true;
    try {
      await api(`/api/admin/knowledge-agents/${reviewing.id}/review`, "POST", {
        revision: reviewing.latest.revision,
        note: event.currentTarget.elements.note.value.trim(),
        approve_reference_use: event.currentTarget.elements.approve_reference_use.checked,
      });
      $("ka-review").close();
      await load();
    } catch (error) {
      $("ka-review-status").textContent = error.message;
    } finally {
      busy = false;
      submit.disabled = false;
    }
  });
  document
    .querySelectorAll("[data-close]")
    .forEach((button) => button.addEventListener("click", () => $(button.dataset.close).close()));
  $("ka-search").addEventListener("input", render);
  $("ka-filter").addEventListener("change", render);
  $("ka-refresh").addEventListener("click", load);
  $("ka-import-button").addEventListener("click", () => $("ka-import-file").click());
  $("ka-import-file").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file || !admin) return;
    $("ka-import-button").disabled = true;
    try {
      if (file.size > 256000) throw new Error("Choose a JSON file no larger than 250 KB.");
      let payload;
      try {
        payload = JSON.parse(await file.text());
      } catch {
        throw new Error("The file does not contain valid JSON.");
      }
      const result = await api("/api/admin/knowledge-agents/import/validate", "POST", payload);
      editor(null, result.definition);
      $("ka-editor-title").textContent = "Import knowledge information";
      $("ka-editor-status").textContent = result.note;
    } catch (error) {
      $("ka-status").textContent = error.message;
    } finally {
      event.target.value = "";
      $("ka-import-button").disabled = !admin;
    }
  });
  $("new-knowledge-agent").addEventListener("click", () => editor());
  window
    .loadWorkspaceProfile()
    .then((profile) => {
      admin = Boolean(profile.is_admin);
      $("new-knowledge-agent").disabled = !admin;
      $("ka-import-button").disabled = !admin;
      $("ka-access").textContent = admin
        ? "Administrators can create, review, publish and withdraw shared knowledge entries."
        : "Shared knowledge entries are visible to your role. An administrator can edit and publish them.";
      render();
    })
    .catch(() => {
      $("ka-access").textContent = "Account permissions could not be loaded.";
    });
  load();
})();
