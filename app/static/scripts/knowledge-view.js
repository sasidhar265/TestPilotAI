(() => {
  const views = {
    saved: ["Saved outputs", "Knowledge", "Browse approved workflow outputs and validated suites. Saved approvals remain visible independently of AI reuse."],
    graph: ["Knowledge graph", "Knowledge", "Explore connected requirements, tests, results and domain references."],
    domain: ["Project knowledge & rules", "Auto finance", "Review configured agent reference documents, product and journey context, and explicitly approved business rules."],
    calculations: ["Calculation checks", "Auto finance", "Validate supplied amounts with explicit arithmetic conventions."],
  };
  let view = new URLSearchParams(location.search).get("view") || "saved";
  if (location.hash === "#finance-tools-title") view = "domain";
  if (location.hash === "#graph-title") view = "graph";
  if (!views[view]) view = "saved";
  document.body.dataset.knowledgeView = view;
  document.querySelectorAll("[data-knowledge-view]").forEach((section) => {
    if (section !== document.body && section.dataset.knowledgeView !== view) section.hidden = true;
  });
  const [title, parent, description] = views[view];
  document.querySelector("h1").textContent = title;
  document.querySelector(".eyebrow").textContent = `${parent} / ${title}`;
  document.querySelector(".page-intro").textContent = description;
  document.title = `${title} · Quality workspace`;
  document.getElementById("service-state").textContent = view === "saved" ? "● Loading source" : "● Workspace tools";
})();
