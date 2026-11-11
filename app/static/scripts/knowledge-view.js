(() => {
  const views = {
    saved: [
      "Saved outputs",
      "Knowledge",
      "Browse approved workflow outputs and validated suites. Saved approvals remain visible independently of AI reuse.",
    ],
    graph: [
      "Knowledge graph",
      "Knowledge",
      "Explore connected requirements, tests, results and domain references.",
    ],
    domain: [
      "Project knowledge & rules",
      "Auto finance",
      "Review configured agent reference documents, product and journey context, and explicitly approved business rules.",
    ],
    calculations: [
      "Calculation checks",
      "Auto finance",
      "Validate supplied amounts with explicit arithmetic conventions.",
    ],
  };
  views.overview = [
    "Knowledge",
    "Workspace",
    "Explore product understanding, remembered context and the guidance that shapes agent behavior.",
  ];
  views.search = [
    "Knowledge",
    "Product understanding",
    "Search accessible reference knowledge, saved workflow records, business rules and standards. This index covers available workspace sources, not arbitrary repositories or external sites.",
  ];
  views.memory = [
    "Memory",
    "Knowledge",
    "Review saved workflow memory and approved outputs. Remembering browser flows and pages per site or app is not configured in this application.",
  ];
  views.domain = [
    "Business view",
    "Product understanding",
    "Review configured products, journeys, business rules and reference terminology. Source approval and profile scope still apply.",
  ];
  let view = new URLSearchParams(location.search).get("view") || "saved";
  if (location.hash === "#finance-tools-title") view = "domain";
  if (location.hash === "#graph-title") view = "graph";
  if (!views[view]) view = "saved";
  document.body.dataset.knowledgeView = view;
  document.querySelectorAll("[data-knowledge-view]").forEach((section) => {
    if (
      section !== document.body &&
      section.dataset.knowledgeView !== (view === "memory" ? "saved" : view)
    )
      section.hidden = true;
  });
  const [title, parent, description] = views[view];
  document.querySelector("h1").textContent = title;
  document.querySelector(".eyebrow").textContent = `${parent} / ${title}`;
  document.querySelector(".page-intro").textContent = description;
  document.title = `${title} · Quality workspace`;
  if (["search", "domain", "memory"].includes(view)) {
    const back = document.createElement("a");
    back.className = "knowledge-back-link";
    back.href = "/knowledge?view=overview";
    back.textContent = "← Knowledge";
    document.querySelector(".topbar").after(back);
  }
  document.getElementById("service-state").textContent = ["saved", "memory"].includes(view)
    ? "● Loading source"
    : "● Workspace tools";
})();
