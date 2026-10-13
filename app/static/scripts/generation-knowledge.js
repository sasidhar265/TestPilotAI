(() => {
  const target = document.getElementById("generation-knowledge-content");
  const status = document.getElementById("generation-knowledge-status");
  const el = (tag, text) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    return node;
  };
  const disclosure = (title, values) => {
    const details = el("details"); details.append(el("summary", title));
    values.forEach((value) => details.append(el("p", value)));
    return details;
  };
  const stages = new Map();
  let revision = 0;
  function render(context) {
    const content = el("div");
    content.append(el("p", context.delivery));
    const domain = context.domain;
    const config = domain.enabled
      ? `${domain.path} · v${domain.version} · ${domain.market} · ${domain.currency} · ${domain.minor_units} decimals · ${domain.rounding}`
      : "Domain pack disabled";
    const configuration = disclosure("Selected domain configuration", [config]);
    configuration.append(el("p", domain.selected
      ? `Products: ${domain.products.map((p) => p.name).join(", ") || "None"} · Journeys: ${domain.journeys.map((j) => j.name).join(", ") || "None"}`
      : "No product, journey or calculation selected. Catalogue scope is not added to the request."));
    [...domain.products, ...domain.journeys].forEach((item) => configuration.append(el("p", `${item.name}: ${item.focus.join("; ")}`)));
    if (domain.calculation) {
      configuration.append(el("p", "Supplied calculation recomputed under the configured reference conventions:"));
      const pre = el("pre", JSON.stringify(domain.calculation, null, 2)); configuration.append(pre);
    }
    content.append(configuration);
    const rules = disclosure("Exact rules and approved business sources", []);
    rules.append(el("p", `Approved domain rules: ${domain.approved_rules.length}. Shared rules: ${context.shared_rules.length}. Request rules: ${context.request_rules.length}.`));
    domain.approved_rules.forEach((r) => rules.append(el("p", `${r.id} v${r.version}: ${r.description} · Owner: ${r.owner} · Source: ${r.source}`)));
    [...context.shared_rules, ...context.request_rules].forEach((r) => rules.append(el("p", `${r.id}: ${r.description}`)));
    context.approved_sources.forEach((s) => rules.append(disclosure(`${s.title} · ${s.id} v${s.version} · ${s.owner}`, [s.content])));
    rules.append(el("p", context.uploaded_brd_present ? "An uploaded BRD receipt is present; the alignment gate verifies it separately." : "No uploaded BRD receipt is present."));
    content.append(rules);
    const topics = disclosure(`Reference topics and exact supplied guidance (${context.topics.length})`, []);
    topics.append(el("p", "These are available reference considerations, not newly approved requirements or a record of model reasoning. Scenario generation receives this knowledge indirectly through reviewed stories."));
    context.topics.forEach((topic) => {
      const entry = disclosure(topic.title, [`${topic.path} · ${topic.authority} · v${topic.version}`, `Source fingerprint: ${topic.fingerprint}`]);
      topic.sections.forEach((section) => {
        const block = disclosure(section.title, []);
        const points = el("div"); points.className = "library-prose";
        window.renderKnowledgeDocument(section.points, points);
        block.append(points); entry.append(block);
      });
      topics.append(entry);
    });
    content.append(topics);
    context.limitations.forEach((message) => content.append(el("p", message)));
    content.append(el("p", context.notice));
    const footer = el("p", `Prepared ${new Date(context.prepared_at).toLocaleString()} · Request: ${context.request_fingerprint} · Context: ${context.fingerprint}`);
    footer.className = "knowledge-context-provenance"; content.append(footer);
    target.replaceChildren();
    if (stages.size > 1) {
      const history = el("div"); history.className = "knowledge-context-stages";
      for (const [stage, snapshot] of stages) {
        const button = el("button", stage.replaceAll("-", " ")); button.type = "button";
        button.className = "secondary"; button.setAttribute("aria-pressed", String(stage === context.stage));
        button.addEventListener("click", () => render(snapshot)); history.append(button);
      }
      target.append(history);
    }
    target.append(content);
    status.textContent = `${context.stage.replaceAll("-", " ")} · ${context.previewRevision !== revision ? "Earlier context — requirements or options changed; preview again." : "Context prepared before operation. Review artifact and validation evidence separately."}`;
  }
  window.addEventListener("generation-knowledge-context", (event) => {
    event.detail.previewRevision = revision; stages.set(event.detail.stage, event.detail); render(event.detail);
  });
  window.addEventListener("generation-knowledge-unavailable", (event) => {
    status.textContent = `Context preview unavailable: ${event.detail}. Previous context may be stale.`;
    target.replaceChildren();
  });
  const invalidate = () => {
    if (!stages.size) return;
    revision += 1;
    status.textContent = "Requirements or options changed. Previous summaries are historical; preview again for current context.";
  };
  ["description", "business-rules", "requirement-file", "business-rules-file", "finance-domain-product", "finance-domain-journey", "output-target", "manual-testing-type", "llm-model"].forEach((id) => {
    document.getElementById(id)?.addEventListener("input", invalidate);
    document.getElementById(id)?.addEventListener("change", invalidate);
  });
  window.addEventListener("workspace-source-replaced", invalidate);
})();
