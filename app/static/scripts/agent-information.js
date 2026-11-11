(() => {
  const view = new URLSearchParams(location.search).get("view");
  const boardView = !view || view === "built-in";
  if (boardView) document.body.dataset.agentLayout = "board";
  let boardFilter = "all";
  const boardColumns = [
    { id: "advice", name: "Advice", description: "Helps you decide what to do", icon: "◇" },
    { id: "builders", name: "Builders", description: "Do the work for you", icon: "✦" },
    { id: "operators", name: "Operators", description: "Run workflow operations", icon: "▷" },
    { id: "custom", name: "Custom agents", description: "Your own specialists", icon: "＋" },
  ];
  const adviceIds = new Set([
    "business-rules-agent",
    "requirements-validation-agent",
    "business-analyst",
    "decision-agent",
    "test-case-validator-agent",
    "metrics-agent",
    "manual-testing-specialist-agent",
  ]);
  const operatorIds = new Set([
    "orchestrator-agent",
    "knowledge-agent",
    "test-storage-agent",
    "execution-agent",
    "automation-execution-agent",
    "output-agent",
  ]);
  function boardCategory(agent) {
    if (isCustom(agent)) return "custom";
    if (adviceIds.has(agent.id)) return "advice";
    return operatorIds.has(agent.id) ? "operators" : "builders";
  }
  const isCustom = (agent) =>
    agent.runtime === "published-knowledge-context" || agent.category === "custom";
  if (boardView || view === "custom") {
    const title = boardView ? "Agents" : "Custom agents";
    document.querySelector(".topbar h1").textContent = title;
    document.getElementById("agents-title").textContent = title;
    document.title = `${title} — Auto Finance Quality`;
    document.querySelector(".agent-directory-hero p").textContent =
      view === "built-in"
        ? "Find the right specialist to advise, build or operate your workflow. Operators work within the application’s approval and permission controls."
        : "Manage browser-local reference definitions and inspect published knowledge contributors for this profile.";
  }
  const list = document.getElementById("agent-list");
  const summary = document.getElementById("agent-summary");
  const refresh = document.getElementById("reload-agents");
  const categories = [
    {
      id: "requirements",
      name: "Requirements & business analysis",
      description: "Prepare requirements, clarify business rules and create grounded stories.",
      agents: [
        "input-agent",
        "business-rules-agent",
        "requirements-validation-agent",
        "business-analyst",
        "story-generator-agent",
      ],
    },
    {
      id: "coordination",
      name: "Planning & coordination",
      description: "Plan the workflow and route work to the appropriate testing specialists.",
      agents: ["orchestrator-agent", "decision-agent"],
    },
    {
      id: "test-design",
      name: "Test design & data",
      description: "Design scenarios, manual and automated test cases, and supporting test data.",
      agents: [
        "scenario-generator-agent",
        "manual-test-case-generator-agent",
        "manual-testing-specialist-agent",
        "automation-test-case-generator-agent",
        "test-data-agent",
      ],
    },
    {
      id: "execution",
      name: "Implementation & execution",
      description: "Build implementation packs and run or summarize controlled test execution.",
      agents: ["multi-language-agent", "execution-agent", "automation-execution-agent"],
    },
    {
      id: "quality",
      name: "Quality & reporting",
      description: "Review test quality, draft defects and calculate quality metrics.",
      agents: ["test-case-validator-agent", "bug-reporter-agent", "metrics-agent"],
    },
    {
      id: "knowledge",
      name: "Knowledge & delivery",
      description:
        "Recall and store approved knowledge, convert test artifacts and deliver outputs.",
      agents: ["knowledge-agent", "context-converter-agent", "output-agent", "test-storage-agent"],
    },
  ];
  const search = document.getElementById("agent-search");
  const categorySelect = document.getElementById("agent-category");
  const clearFilters = document.getElementById("clear-agent-filters");
  const message = document.getElementById("agent-directory-message");
  const customDialog = document.getElementById("custom-agent-dialog");
  const detailDialog = document.getElementById("agent-detail-dialog");
  const customForm = document.getElementById("custom-agent-form");
  const customStatus = document.getElementById("custom-agent-status");
  const customStorageKey = "quality-workspace-custom-agent-definitions-v1";
  const extraCategories = [
    {
      id: "other",
      name: "Other registered agents",
      description: "Additional registered components.",
    },
    {
      id: "custom",
      name: "Custom definitions",
      description: "Reference definitions saved in this browser.",
    },
  ];
  const expandedSections = new Map();
  let registered = [];
  let custom = [];
  const symbols = {
    requirements: "◇",
    coordination: "⌘",
    "test-design": "✦",
    execution: "▷",
    quality: "✓",
    knowledge: "◈",
    other: "◎",
    custom: "＋",
  };
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function readCustomAgents() {
    const records = JSON.parse(localStorage.getItem(customStorageKey) || "[]");
    if (
      !Array.isArray(records) ||
      records.some(
        (record) =>
          !record ||
          ["name", "purpose", "instructions"].some((key) => typeof record[key] !== "string"),
      )
    )
      throw new Error();
    return records;
  }
  function categoryFor(agent) {
    return [...categories, ...extraCategories].find((category) => category.id === agent.category);
  }
  function allAgents() {
    return [
      ...registered.map((agent) => ({
        ...agent,
        category:
          categories.find((category) => category.agents.includes(agent.id))?.id ||
          (agent.kind === "knowledge" ? "knowledge" : "other"),
      })),
      ...custom.map((agent, index) => ({
        ...agent,
        id: `custom-${index}`,
        category: "custom",
        kind: "Reference definition",
        runtime: "Browser storage",
        capabilities: [],
      })),
    ].filter((agent) => (view === "custom" ? isCustom(agent) : true));
  }
  function showDetails(agent) {
    document.getElementById("agent-detail-title").textContent = agent.name;
    const content = document.getElementById("agent-detail-content");
    const details = element("dl", undefined, "agent-detail-metadata");
    const fields = [
      ["Category", categoryFor(agent).name],
      ["Role", agent.kind],
      ["Runtime", agent.runtime],
    ];
    if (agent.category !== "custom")
      fields.push(
        ["Agent ID", agent.id],
        ["Instruction reference", agent.instruction_file || "No instruction file registered"],
      );
    for (const [label, value] of fields) {
      const row = element("div");
      row.append(element("dt", label), element("dd", value));
      details.append(row);
    }
    content.replaceChildren(element("p", agent.purpose, "agent-detail-purpose"), details);
    if (agent.capabilities.length) {
      const capabilities = element("ul", undefined, "agent-capabilities");
      capabilities.append(...agent.capabilities.map((capability) => element("li", capability)));
      content.append(element("h3", "Capabilities"), capabilities);
    }
    if (agent.category === "custom")
      content.append(
        element("h3", "Instructions"),
        element("p", agent.instructions, "agent-custom-instructions"),
        element("p", "Reference only · Saved in this browser", "agent-directory-note"),
      );
    detailDialog.showModal();
  }
  function renderCard(agent) {
    const card = element("article", undefined, "agent-directory-card");
    card.dataset.category = agent.category;
    const head = element("div", undefined, "agent-card-header");
    const icon = element("span", symbols[agent.category], "agent-avatar");
    icon.setAttribute("aria-hidden", "true");
    head.append(icon, element("span", categoryFor(agent).name, "agent-category-badge"));
    const button = element("button", "View details ↗", "agent-details-button");
    button.type = "button";
    button.setAttribute("aria-label", `View details for ${agent.name}`);
    button.addEventListener("click", () => showDetails(agent));
    const footer = element("div", undefined, "agent-card-footer");
    footer.append(
      element(
        "span",
        agent.category === "custom"
          ? "Reference definition"
          : `${agent.capabilities.length} capabilities`,
      ),
      button,
    );
    card.append(
      head,
      element("h4", agent.name, "agent-card-name"),
      element("p", agent.purpose, "agent-card-purpose"),
      footer,
    );
    return card;
  }
  function renderBoard() {
    const agents = allAgents();
    const query = search.value.trim().toLocaleLowerCase();
    const filtered = agents.filter(
      (agent) =>
        (boardFilter === "all" || boardCategory(agent) === boardFilter) &&
        [
          agent.name,
          agent.purpose,
          agent.kind,
          agent.runtime,
          categoryFor(agent).name,
          ...agent.capabilities,
        ]
          .join(" ")
          .toLocaleLowerCase()
          .includes(query),
    );
    const columns = boardColumns
      .filter((column) => boardFilter === "all" || column.id === boardFilter)
      .map((column) => {
        const section = element("section", undefined, "agent-board-column");
        section.dataset.boardCategory = column.id;
        const members = filtered.filter((agent) => boardCategory(agent) === column.id);
        const heading = element("div", undefined, "agent-board-column-heading");
        const title = element("h3", column.name);
        title.id = `board-${column.id}-title`;
        section.setAttribute("aria-labelledby", title.id);
        heading.append(title, element("span", String(members.length), "agent-section-count"));
        const description = element("p", column.description, "agent-board-description");
        section.append(heading, description);
        if (column.id === "custom") {
          const create = element("button", "+ New", "button agent-board-new");
          create.type = "button";
          create.setAttribute("aria-label", "New custom agent");
          create.addEventListener("click", () =>
            document.getElementById("open-custom-agent").click(),
          );
          section.append(create);
        }
        for (const agent of members) {
          const card = element("button", undefined, "agent-board-agent");
          card.type = "button";
          card.dataset.agentId = agent.id;
          card.setAttribute("aria-label", `View details for ${agent.name}`);
          const icon = element("span", symbols[agent.category], "agent-avatar");
          icon.setAttribute("aria-hidden", "true");
          const copy = element("span", undefined, "agent-board-copy");
          copy.append(element("strong", agent.name), element("span", agent.purpose));
          card.append(icon, copy);
          card.addEventListener("click", () => showDetails(agent));
          section.append(card);
        }
        if (!members.length) {
          const hasCustom = agents.some((agent) => boardCategory(agent) === "custom");
          section.append(
            element(
              "p",
              column.id === "custom" && !hasCustom ? "No custom agents" : "No matching agents",
              "agent-board-empty",
            ),
          );
        }
        return section;
      });
    list.classList.add("agent-board");
    list.classList.toggle("agent-board-filtered", boardFilter !== "all");
    list.replaceChildren(...columns);
    summary.textContent = `${filtered.length} of ${agents.length} agents`;
    document.getElementById("registered-agent-count").textContent = registered.filter(
      (agent) => !isCustom(agent),
    ).length;
    document.getElementById("custom-agent-count").textContent = agents.filter(isCustom).length;
    clearFilters.hidden = !query && boardFilter === "all";
    document
      .querySelectorAll("[data-agent-filter]")
      .forEach((button) =>
        button.setAttribute("aria-pressed", String(button.dataset.agentFilter === boardFilter)),
      );
  }
  function render() {
    if (boardView) {
      renderBoard();
      return;
    }
    const agents = allAgents();
    const query = search.value.trim().toLocaleLowerCase();
    const selected = categorySelect.value;
    const filtered = agents.filter(
      (agent) =>
        (selected === "all" || selected === agent.category) &&
        [
          agent.name,
          agent.purpose,
          agent.kind,
          agent.runtime,
          categoryFor(agent).name,
          ...agent.capabilities,
        ]
          .join(" ")
          .toLocaleLowerCase()
          .includes(query),
    );
    const sections = [...categories, ...extraCategories].flatMap((category) => {
      const members = filtered.filter((agent) => agent.category === category.id);
      if (!members.length) return [];
      const section = element("details", undefined, "agent-category-section");
      section.dataset.category = category.id;
      section.open = Boolean(query || selected !== "all" || expandedSections.get(category.id));
      section.addEventListener("toggle", () => {
        if (section.isConnected && !search.value.trim() && categorySelect.value === "all")
          expandedSections.set(category.id, section.open);
      });
      const heading = element("h3", category.name);
      heading.id = `agent-section-${category.id}`;
      section.setAttribute("aria-labelledby", heading.id);
      const header = element("summary", undefined, "agent-category-heading");
      const count = element("span", String(members.length), "agent-section-count");
      count.setAttribute("aria-label", `${members.length} agents and definitions`);
      header.append(heading, count);
      const grid = element("div", undefined, "agent-directory-grid");
      grid.append(...members.map(renderCard));
      const content = element("div", undefined, "agent-category-content");
      content.append(element("p", category.description, "agent-category-description"), grid);
      section.append(header, content);
      return [section];
    });
    list.replaceChildren(...sections);
    if (!filtered.length) {
      const empty = element("div", undefined, "agent-directory-empty");
      empty.append(
        element("h3", agents.length ? "No matching agents" : "No agents to show"),
        element(
          "p",
          agents.length
            ? "Try a different search or category."
            : "Refresh the directory or add a custom definition.",
        ),
      );
      list.append(empty);
    }
    summary.textContent = `${filtered.length} of ${agents.length} agents and definitions`;
    document.getElementById("registered-agent-count").textContent = agents.filter(
      (agent) => agent.category !== "custom",
    ).length;
    document.getElementById("agent-category-count").textContent = new Set(
      agents.filter((agent) => agent.category !== "custom").map((agent) => agent.category),
    ).size;
    document.getElementById("custom-agent-count").textContent = custom.length;
    clearFilters.hidden = !query && selected === "all";
  }
  function updateCategories() {
    const selected = categorySelect.value;
    const agents = allAgents();
    categorySelect.replaceChildren(new Option("All categories", "all"));
    for (const category of [...categories, ...extraCategories]) {
      const count = agents.filter((agent) => agent.category === category.id).length;
      if (count || (category.id === "custom" && view !== "built-in"))
        categorySelect.add(new Option(`${category.name} (${count})`, category.id));
    }
    categorySelect.value = [...categorySelect.options].some((option) => option.value === selected)
      ? selected
      : "all";
  }
  for (const [id, open] of [
    ["expand-agent-sections", true],
    ["collapse-agent-sections", false],
  ]) {
    document.getElementById(id).addEventListener("click", () => {
      for (const section of list.querySelectorAll("details[data-category]")) {
        expandedSections.set(section.dataset.category, open);
        section.open = open;
      }
    });
  }
  search.addEventListener("input", render);
  categorySelect.addEventListener("change", render);
  clearFilters.addEventListener("click", () => {
    search.value = "";
    categorySelect.value = "all";
    boardFilter = "all";
    render();
    search.focus();
  });
  document.getElementById("open-custom-agent").addEventListener("click", () => {
    customStatus.textContent = "";
    customDialog.showModal();
  });
  document
    .getElementById("close-custom-agent")
    .addEventListener("click", () => customDialog.close());
  document
    .getElementById("close-agent-details")
    .addEventListener("click", () => detailDialog.close());
  for (const dialog of [customDialog, detailDialog])
    dialog.addEventListener("click", (event) => {
      if (event.target !== dialog) return;
      const bounds = dialog.getBoundingClientRect();
      if (
        event.clientX < bounds.left ||
        event.clientX > bounds.right ||
        event.clientY < bounds.top ||
        event.clientY > bounds.bottom
      )
        dialog.close();
    });
  customForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(customForm);
    const agent = Object.fromEntries(
      ["name", "purpose", "instructions"].map((key) => [key, String(data.get(key) || "").trim()]),
    );
    if (Object.values(agent).some((value) => !value)) {
      customStatus.textContent = "Enter a name, purpose and instructions.";
      return;
    }
    try {
      const records = readCustomAgents();
      if (
        records.some((record) => record.name.toLocaleLowerCase() === agent.name.toLocaleLowerCase())
      ) {
        customStatus.textContent = "A custom definition with this name already exists.";
        return;
      }
      localStorage.setItem(customStorageKey, JSON.stringify([...records, agent]));
      custom = [...records, agent];
      customForm.reset();
      search.value = "";
      categorySelect.value = "custom";
      updateCategories();
      categorySelect.value = "custom";
      render();
      customDialog.close();
      message.textContent = `${agent.name} saved in this browser.`;
    } catch {
      customStatus.textContent =
        "The definition could not be saved. Check browser storage and try again.";
    }
  });
  async function load() {
    refresh.disabled = true;
    list.setAttribute("aria-busy", "true");
    summary.textContent = "Loading registered agents…";
    try {
      const response = await fetch("/api/agents", {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error();
      registered = await response.json();
      message.textContent = "";
      updateCategories();
      render();
      const status = document.querySelector("#status .status-copy");
      if (status) status.textContent = `${registered.length} registered agents`;
    } catch {
      render();
      message.textContent =
        "Registered agents could not be refreshed. Check your connection and select Refresh to retry.";
    } finally {
      refresh.disabled = false;
      list.setAttribute("aria-busy", "false");
    }
  }
  try {
    custom = readCustomAgents();
  } catch {
    message.textContent =
      "Custom definitions could not be read. Browser storage must be available.";
  }
  if (boardView) {
    const tools = document.querySelector(".agent-directory-tools");
    const controls = element("div", undefined, "agent-board-controls");
    const filters = element("div", undefined, "agent-board-filters");
    filters.setAttribute("role", "group");
    filters.setAttribute("aria-label", "Filter agents by function");
    for (const column of [{ id: "all", name: "All agents" }, ...boardColumns]) {
      const button = element("button", column.name, "agent-filter-button");
      button.type = "button";
      button.dataset.agentFilter = column.id;
      button.setAttribute("aria-pressed", String(column.id === boardFilter));
      button.addEventListener("click", () => {
        boardFilter = column.id;
        render();
      });
      filters.append(button);
    }
    controls.append(tools, filters);
    document.querySelector(".agent-directory-hero").append(controls);
    document.querySelector(".agent-directory-note").textContent =
      "Operators run within existing workflow approvals and permissions. Custom definitions saved in this browser are reference-only; published knowledge contributors supply reviewed context to the governed workflow.";
  }
  if (view === "custom" && new URLSearchParams(location.search).has("create"))
    customDialog.showModal();
  updateCategories();
  refresh.addEventListener("click", load);
  load();
})();
