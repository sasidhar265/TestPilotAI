(() => {
  if (document.body.dataset.knowledgeView !== "domain") return;
  const $ = (id) => document.getElementById(id);
  const node = (tag, text, cls) => {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (cls) element.className = cls;
    return element;
  };
  const topics = {
    "auto-finance-products.md": ["Products", "◇", "Understand finance and rental models, payment structures and product approval questions."],
    "auto-finance-lifecycle.md": ["Journeys", "↗", "Follow the customer journey from quotation through underwriting, servicing and closure."],
    "auto-finance-calculations-and-data.md": ["Calculations", "∑", "Explore calculation conventions, golden examples, data ownership and execution evidence."],
    "auto-finance-governance-and-gaps.md": ["Governance", "◎", "Review policy ownership, open approvals and the path from reference guidance to approved rules."],
    "quotation-brd-baseline.md": ["Quotation", "▤", "Review the draft quotation requirements, validation errors and financial expectations."],
    "quotation-risk-and-evidence.md": ["Quotation", "◈", "Explore financial edge cases and the independent evidence needed to test them."],
    "quotation-services-product-catalog.md": ["Products", "◇", "Browse the canonical products, brands and maintenance codes used by this project."],
  };
  let sources = [], active = "All topics";
  const read = (source) => {
    const reader = $("domain-reader"); reader.replaceChildren();
    const header = node("div", "", "library-reader-header");
    const label = node("span", "Reference guidance · Business approval pending", "library-badge");
    const close = node("button", "Close article", "secondary"); close.type = "button";
    close.addEventListener("click", () => {
      reader.hidden = true;
      const button = [...$("domain-library").querySelectorAll("button")].find((b) => b.dataset.source === source.id);
      (button || $("domain-library-search")).focus();
    });
    header.append(label, close);
    reader.append(header, node("h2", source.title));
    reader.querySelector("h2").id = "domain-reader-title";
    const body = node("div", "", "library-prose"); window.renderKnowledgeDocument(source.content, body); reader.append(body);
    const provenance = node("details", "", "library-provenance");
    provenance.append(node("summary", "Source and document details"));
    provenance.append(node("p", source.path));
    source.content.split("\n").filter((line) => /^(Version|Status|Owner|Reviewed|Scope|Authority|Source):/.test(line)).forEach((line) => provenance.append(node("p", line)));
    reader.append(provenance); reader.hidden = false; reader.focus();
    reader.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const render = () => {
    const query = $("domain-library-search").value.trim().toLowerCase();
    const matching = sources.filter((source) => (active === "All topics" || (topics[source.id]?.[0] || "Reference") === active) && `${source.title} ${source.content}`.toLowerCase().includes(query));
    $("domain-library").replaceChildren();
    matching.forEach((source) => {
      const [category, symbol, description] = topics[source.id] || ["Reference", "▤", "Explore project reference knowledge and source details."];
      const card = node("article", "", "library-topic-card");
      const top = node("div", "", "library-card-top"); top.append(node("span", symbol, "library-icon"), node("span", category, "library-category"));
      const button = node("button", "Explore topic →", "secondary"); button.type = "button"; button.dataset.source = source.id;
      button.setAttribute("aria-label", `Explore ${source.title}`); button.addEventListener("click", () => read(source));
      card.append(top, node("h4", source.title), node("p", description), node("span", "Reference · Approval pending", "library-badge"), button);
      $("domain-library").append(card);
    });
    if (!matching.length) $("domain-library").append(node("p", "No topics match. Try another search or choose All topics.", "section-copy"));
    $("domain-library-status").textContent = `${matching.length} of ${sources.length} topics · Reference knowledge used by agents`;
  };
  $("domain-library-search").addEventListener("input", render);
  fetch("/api/workspace/knowledge", { credentials: "same-origin", cache: "no-store" })
    .then((response) => { if (!response.ok) throw new Error("Knowledge unavailable. Refresh to retry."); return response.json(); })
    .then((data) => {
      sources = data.domain_library || [];
      ["All topics", ...new Set(sources.map((source) => topics[source.id]?.[0] || "Reference"))].forEach((category) => {
        const button = node("button", category); button.type = "button"; button.setAttribute("aria-pressed", String(category === active));
        button.addEventListener("click", () => {
          active = category;
          $("domain-library-filters").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
          render();
        });
        $("domain-library-filters").append(button);
      });
      render();
    }).catch((error) => { $("domain-library-status").textContent = error.message; });
})();
