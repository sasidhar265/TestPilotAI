const formatDate = (value) => {
  if (!value) return "—";
  return new Date(value).toLocaleString();
};

const cell = (value) => {
  const node = document.createElement("td");
  node.textContent = value ?? "—";
  return node;
};

const renderRows = (target, rows, columns, emptyText, source, identifierField) => {
  target.replaceChildren();
  if (!rows.length) {
    const row = document.createElement("tr");
    const empty = document.createElement("td");
    empty.colSpan = columns;
    empty.className = "empty";
    empty.textContent = emptyText;
    row.append(empty);
    target.append(row);
    return;
  }
  rows.forEach((item) => {
    const row = document.createElement("tr");
    const { identifier, ...visible } = item;
    Object.values(visible).forEach((value) => row.append(cell(value)));
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.className = "secondary inspect-button";
    button.type = "button";
    button.textContent = "View data";
    button.dataset.source = source;
    button.dataset.identifier = item[identifierField] || identifier;
    action.append(button);
    row.append(action);
    target.append(row);
  });
};

const loadKnowledge = async () => {
  const response = await fetch("/api/workspace/knowledge", { credentials: "same-origin" });
  if (!response.ok) throw new Error("Knowledge source unavailable");
  const data = await response.json();
  document.querySelector("#suite-count").textContent = data.suite_count;
  document.querySelector("#output-count").textContent = data.approved_output_count;
  document.querySelector("#scenario-count").textContent = data.scenario_count;
  document.querySelector("#memory-status").textContent = data.enabled ? "Enabled" : "Disabled";
  renderRows(document.querySelector("#suite-list"), data.suites.map((item) => ({
    feature: item.feature, cases: item.cases, key: item.memory_key,
    accessed: formatDate(item.last_accessed_at), uses: item.access_count,
    identifier: item.memory_key,
  })), 6, "No suites are stored yet.", "suites", "identifier");
  renderRows(document.querySelector("#output-list"), data.approved_outputs.map((item) => ({
    feature: item.feature, filename: item.filename, format: item.format,
    cases: item.cases, created: formatDate(item.created_at),
    identifier: item.artifact_id,
  })), 6, "No approved converted outputs are stored yet.", "outputs", "identifier");
  document.querySelector("#service-state").textContent = "● Source available";
};

const showDetail = async (source, identifier) => {
  const response = await fetch(`/api/workspace/knowledge/${source}/${encodeURIComponent(identifier)}`, { credentials: "same-origin" });
  if (!response.ok) throw new Error("Stored entry unavailable");
  const data = await response.json();
  const detail = data.suite || data.output;
  document.querySelector("#detail-title").textContent = detail.feature || detail.filename || "Entry details";
  document.querySelector("#detail-summary").textContent = detail.filename ? `${detail.filename} · ${detail.format}` : `Memory key ${detail.memory_key}`;
  document.querySelector("#detail-content").textContent = JSON.stringify(detail, null, 2);
  const panel = document.querySelector("#knowledge-detail");
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
};

document.addEventListener("click", (event) => {
  const button = event.target.closest(".inspect-button");
  if (!button) return;
  showDetail(button.dataset.source, button.dataset.identifier).catch((error) => {
    document.querySelector("#knowledge-status").textContent = error.message;
  });
});
document.querySelector("#close-detail").addEventListener("click", () => {
  document.querySelector("#knowledge-detail").hidden = true;
});

loadKnowledge().catch((error) => {
  document.querySelector("#service-state").textContent = "● Source unavailable";
  document.querySelector("#knowledge-status").textContent = error.message;
});
