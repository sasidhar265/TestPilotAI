/* Build relationships only from explicit, versioned lifecycle records. */
(() => {
  const types = [
    "project",
    "requirement",
    "baseline",
    "suite",
    "test",
    "cycle",
    "result",
    "defect",
    "domain",
    "product",
    "journey",
    "rule",
  ];
  const id = (kind, ...parts) =>
    `${kind}:${parts.map((part) => encodeURIComponent(part)).join("/")}`;
  function build(snapshot, project = "") {
    const nodes = new Map(),
      links = new Map();
    const rows = (key) => snapshot[key] || [];
    const belongs = (row) => !project || row.project === project;
    const add = (kind, key, label, fields = {}) => {
      const identifier = id(kind, ...key);
      nodes.set(identifier, { id: identifier, kind, label, fields });
      return identifier;
    };
    const link = (source, target, relation) => {
      if (nodes.has(source) && nodes.has(target))
        links.set(`${source}|${target}|${relation}`, { source, target, relation });
    };
    const projects = [
      ...new Set(
        [...rows("requirements"), ...rows("baselines"), ...rows("suites"), ...rows("cycles")]
          .map((row) => row.project)
          .filter(Boolean),
      ),
    ].sort();
    projects
      .filter((name) => !project || name === project)
      .forEach((name) => add("project", [name], name));
    rows("requirements")
      .filter(belongs)
      .forEach((row) => {
        const key = add("requirement", [row.id], `${row.key} · v${row.version}`, {
          title: row.title,
          description: row.description,
          status: row.status,
          owner: row.owner,
          source: row.source,
          project: row.project,
        });
        link(id("project", row.project), key, "contains");
      });
    const baselines = new Map(
      rows("baselines")
        .filter(belongs)
        .map((row) => [row.id, row]),
    );
    baselines.forEach((row) => {
      const key = add("baseline", [row.id], row.name, { status: row.status, project: row.project });
      (row.requirements || []).forEach((requirement) =>
        link(id("requirement", requirement.id), key, "included in"),
      );
    });
    rows("suites")
      .filter(belongs)
      .forEach((row) => {
        const key = add("suite", [row.id], row.suite.feature_name, {
          status: row.status,
          project: row.project,
        });
        link(id("baseline", row.baseline_id), key, "defines");
        (row.suite.test_cases || []).forEach((test) => {
          const testKey = add("test", [row.id, test.id], test.id, {
            title: test.title,
            category: test.category,
            priority: test.priority,
            mode: test.execution_mode,
            project: row.project,
          });
          link(key, testKey, "contains");
          const baseline = baselines.get(row.baseline_id);
          (row.mappings[test.id] || []).forEach((requirementKey) => {
            const requirement = baseline?.requirements.find(
              (entry) => entry.key === requirementKey,
            );
            if (requirement) link(id("requirement", requirement.id), testKey, "covered by");
          });
        });
      });
    const cycles = new Map(
      rows("cycles")
        .filter(belongs)
        .map((row) => [row.id, row]),
    );
    cycles.forEach((row) => {
      const key = add("cycle", [row.id], row.name, {
        build: row.build,
        environment: row.environment,
        project: row.project,
      });
      link(id("suite", row.suite_id), key, "executed in");
    });
    rows("attempts").forEach((row) => {
      const cycle = cycles.get(row.cycle_id);
      if (!cycle) return;
      const key = add("result", [row.id], `${row.case_id} · ${row.status}`, {
        status: row.status,
        actual: row.actual,
        source: row.source,
        build: cycle.build,
        environment: cycle.environment,
        recorded: row.created_at,
        project: cycle.project,
      });
      link(id("cycle", row.cycle_id), key, "records");
      link(id("test", cycle.suite_id, row.case_id), key, "has result");
    });
    rows("attempts").forEach((row) => {
      if (row.retest_of) link(id("result", row.retest_of), id("result", row.id), "retested by");
    });
    rows("defects").forEach((row) => {
      const cycle = cycles.get(row.cycle_id);
      if (!cycle || !nodes.has(id("result", row.attempt_id))) return;
      const key = add("defect", [row.id], row.title, {
        status: row.status,
        severity: row.severity,
        jira: row.jira_key,
        project: cycle.project,
      });
      link(id("result", row.attempt_id), key, "raised");
    });
    const domain = snapshot.finance_domain;
    if (domain) {
      const domainId = add("domain", [domain.version], "Auto-finance domain", {
        version: domain.version,
        market: domain.market,
        status: "reference catalogue",
        currency: domain.currency,
      });
      (domain.products || []).forEach((item) => {
        const key = add("product", [item.id], `${item.id} · ${item.name}`, {
          status: "reference",
          focus: (item.focus || []).join(" · "),
        });
        link(domainId, key, "catalogues");
      });
      (domain.journeys || []).forEach((item) => {
        const key = add("journey", [item.id], item.name, {
          status: "reference",
          focus: (item.focus || []).join(" · "),
        });
        link(domainId, key, "catalogues");
      });
      (domain.rules || []).forEach((rule) => {
        const key = add("rule", [rule.id, rule.version], `${rule.id} · v${rule.version}`, {
          status: rule.status,
          description: rule.description,
          owner: rule.owner,
          source: rule.source,
        });
        link(domainId, key, "records rule");
        (rule.product_ids || []).forEach((product) =>
          link(id("product", product), key, "scopes rule"),
        );
        (rule.journey_ids || []).forEach((journey) =>
          link(id("journey", journey), key, "scopes rule"),
        );
      });
      (domain.mappings || []).filter(belongs).forEach((mapping) => {
        rows("requirements")
          .filter(
            (row) =>
              row.project === mapping.project &&
              row.key === mapping.requirement_key &&
              row.version === mapping.requirement_version,
          )
          .forEach((row) => {
            const req = id("requirement", row.id);
            link(id("product", mapping.product_id), req, "classifies");
            mapping.journey_ids.forEach((journey) =>
              link(id("journey", journey), req, "includes requirement"),
            );
            mapping.rule_ids.forEach((ruleId) => {
              const rule = domain.rules.find(
                (item) => item.id === ruleId && item.status === "approved",
              );
              if (rule) link(id("rule", rule.id, rule.version), req, "explicitly mapped to");
            });
          });
      });
      rows("suites")
        .filter(belongs)
        .forEach((row) => {
          const baseline = baselines.get(row.baseline_id);
          (row.suite.test_cases || []).forEach((test) => {
            (test.acceptance_criteria_covered || []).forEach((ruleId) => {
              const rule = domain.rules.find(
                (item) => item.id === ruleId && item.status === "approved",
              );
              const pinned = domain.mappings.some(
                (mapping) =>
                  mapping.project === row.project &&
                  mapping.rule_ids.includes(ruleId) &&
                  baseline?.requirements.some(
                    (req) =>
                      req.key === mapping.requirement_key &&
                      req.version === mapping.requirement_version,
                  ) &&
                  (row.mappings[test.id] || []).includes(mapping.requirement_key),
              );
              if (rule && pinned)
                link(
                  id("rule", rule.id, rule.version),
                  id("test", row.id, test.id),
                  "explicit coverage",
                );
            });
          });
        });
    }
    return { nodes: [...nodes.values()], links: [...links.values()], projects };
  }
  const example = {
    requirements: [
      {
        id: "example-requirement",
        project: "Example project",
        key: "REQ-001",
        version: 1,
        title: "Service availability",
        description: "Illustrative requirement for the graph preview.",
        status: "approved",
      },
    ],
    baselines: [
      {
        id: "example-baseline",
        project: "Example project",
        name: "Reviewed baseline",
        status: "approved",
        requirements: [{ id: "example-requirement", key: "REQ-001" }],
      },
    ],
    suites: [
      {
        id: "example-suite",
        project: "Example project",
        baseline_id: "example-baseline",
        status: "approved",
        mappings: { "TC-001": ["REQ-001"] },
        suite: {
          feature_name: "Service checks",
          test_cases: [
            {
              id: "TC-001",
              title: "Service availability check",
              category: "smoke",
              priority: "P1",
              execution_mode: "automation",
            },
          ],
        },
      },
    ],
    cycles: [
      {
        id: "example-cycle",
        project: "Example project",
        suite_id: "example-suite",
        name: "Example cycle",
        build: "Illustrative build",
        environment: "Example environment",
      },
    ],
    attempts: [
      {
        id: "example-result",
        cycle_id: "example-cycle",
        case_id: "TC-001",
        status: "failed",
        actual: "Illustrative result, not an executed test.",
        source: "example",
      },
    ],
    defects: [
      {
        id: "example-defect",
        cycle_id: "example-cycle",
        attempt_id: "example-result",
        title: "Example defect",
        severity: "minor",
        status: "open",
      },
    ],
  };
  // A spanning forest gives every record one place, including disconnected records
  // and cycles. Cross-links remain available in the full graph and inspector.
  function forest(nodes, links) {
    const visited = new Set(),
      edges = [],
      placements = new Map();
    let leaf = 0;
    function visit(node, depth) {
      visited.add(node.id);
      const children = [];
      links
        .filter((edge) => edge.source === node.id)
        .forEach((edge) => {
          const child = nodes.find((entry) => entry.id === edge.target);
          if (child && !visited.has(child.id)) {
            edges.push(edge);
            visit(child, depth + 1);
            children.push(placements.get(child.id));
          }
        });
      const x = children.length
        ? (children[0].x + children[children.length - 1].x) / 2
        : 30 + leaf++ * 230;
      placements.set(node.id, { x, y: 40 + depth * 135 });
    }
    const roots = nodes.filter((node) => !links.some((edge) => edge.target === node.id));
    [...roots, ...nodes].forEach((node) => {
      if (!visited.has(node.id)) visit(node, 0);
    });
    return { edges, placements };
  }
  function markdown(nodes, links, tree = false) {
    const ids = new Map(nodes.map((node, index) => [node.id, `n${index}`]));
    const escape = (value) =>
      String(value).replace(
        /[&<>"\r\n]/g,
        (char) =>
          ({
            "&": "&#38;",
            "<": "&#60;",
            ">": "&#62;",
            '"': "&#34;",
            "\r": " ",
            "\n": " ",
          })[char],
      );
    return [
      "# Business model knowledge graph",
      "",
      "```mermaid",
      `flowchart ${tree ? "TD" : "LR"}`,
      ...nodes.map(
        (node) => `  ${ids.get(node.id)}["${escape(node.kind)}: ${escape(node.label)}"]`,
      ),
      ...links.map(
        (edge) =>
          `  ${ids.get(edge.source)} -->|"${escape(edge.relation)}"| ${ids.get(edge.target)}`,
      ),
      "```",
      "",
    ].join("\n");
  }
  const api = { build, types, example, forest, markdown };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else window.KnowledgeGraphData = api;
})();
