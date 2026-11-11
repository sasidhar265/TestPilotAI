/* Search accessible workspace sources without adding a second store or approval path. */
(async () => {
  if (document.body.dataset.knowledgeView !== "search") return;
  const $ = (id) => document.getElementById(id);
  const records = [];
  let failures = 0;
  const node = (tag, text) => {
    const element = document.createElement(tag);
    element.textContent = text;
    return element;
  };
  function add(type, title, content, href, status) {
    records.push({
      type,
      title,
      content,
      href,
      status,
      index: `${title} ${content}`.toLowerCase(),
    });
  }
  function render() {
    const query = $("knowledge-everything-search").value.trim().toLowerCase();
    const type = $("knowledge-source-filter").value;
    const matches = records.filter(
      (record) => (type === "all" || type === record.type) && record.index.includes(query),
    );
    $("knowledge-search-results").replaceChildren(
      ...matches.slice(0, 100).map((record) => {
        const card = node("article", "");
        card.className = "knowledge-search-card";
        const title = node("a", record.title);
        title.href = record.href;
        const excerpt = node("p", record.content.slice(0, 320));
        card.append(node("small", record.status), node("h3", ""), excerpt);
        card.querySelector("h3").append(title);
        return card;
      }),
    );
    $("knowledge-search-status").textContent =
      `${matches.length} matching records${matches.length > 100 ? " · showing the first 100; narrow your search" : ""}.${failures ? ` ${failures} source(s) unavailable; results are incomplete. Reload to retry.` : ""} Reference content and saved record summaries are indexed; private repositories and site/page captures are not included.`;
    if (!matches.length)
      $("knowledge-search-results").append(
        node("p", "No matching knowledge. Try another search or source filter."),
      );
  }
  const tasks = [
    [
      "/api/knowledge-agents",
      (data) => {
        for (const item of data.agents || []) {
          const versions = [item.published, item.latest].filter(
            (version, index, values) =>
              version &&
              values.findIndex((entry) => entry?.revision === version.revision) === index,
          );
          for (const version of versions) {
            const definition = version.definition;
            add(
              "reference",
              definition.name,
              `${definition.purpose}\n${definition.instructions}\n${definition.knowledge}\n${definition.source_reference}`,
              "/knowledge-agents",
              `${item.published?.revision === version.revision ? "Published reference" : "Draft reference · not active"} · ${definition.profile} · v${version.revision}`,
            );
          }
        }
      },
    ],
    [
      "/api/workspace/knowledge",
      (data) => {
        for (const source of data.domain_library || [])
          add(
            "reference",
            source.title,
            source.content || "",
            "/knowledge?view=domain",
            "Profile reference · source approval applies",
          );
        for (const [field, key] of [
          ["suites", "memory_key"],
          ["approved_outputs", "artifact_id"],
        ]) {
          for (const item of data[field] || [])
            add(
              "memory",
              item.feature || item.title || item[key] || "Saved record",
              JSON.stringify(item),
              field === "suites"
                ? "/knowledge?view=memory"
                : `/knowledge?artifact=${encodeURIComponent(item[key] || "")}`,
              "Saved workflow record · summary",
            );
        }
      },
    ],
    [
      "/api/workspace/rules",
      (data) => {
        for (const rule of data.business_rules || [])
          add(
            "rule",
            rule.id || rule.name || "Business rule",
            JSON.stringify(rule),
            "/knowledge?view=domain",
            "Business rule · review source approval",
          );
      },
    ],
    [
      "/api/workspace/standards",
      (data) => {
        for (const [name, content] of Object.entries(data))
          if (typeof content === "string")
            add(
              "standard",
              `${name} standards`,
              content,
              "/documentation#knowledge-skills",
              "Workspace standards",
            );
      },
    ],
  ];
  await Promise.all(
    tasks.map(async ([path, consume]) => {
      try {
        const response = await fetch(path, { cache: "no-store" });
        if (!response.ok) throw new Error();
        consume(await response.json());
      } catch {
        failures++;
      }
    }),
  );
  $("knowledge-everything-search").addEventListener("input", render);
  $("knowledge-source-filter").addEventListener("change", render);
  render();
})();
