const assert = require("node:assert/strict");
const {
  build,
  example,
  forest,
  markdown,
} = require("../../app/static/scripts/knowledge-graph-data.js");

const empty = build({});
assert.equal(empty.nodes.length, 0);
assert.equal(empty.links.length, 0);
const snapshot = JSON.parse(JSON.stringify(example));
const initial = build(snapshot);
assert.equal(initial.nodes.length, 8);
assert.equal(initial.links.length, 9);
assert(
  initial.links.every(
    (edge) =>
      initial.nodes.some((node) => node.id === edge.source) &&
      initial.nodes.some((node) => node.id === edge.target),
  ),
);

snapshot.requirements.push({ ...snapshot.requirements[0], id: "new-version", version: 2 });
const versions = build(snapshot);
const test = versions.nodes.find((node) => node.kind === "test");
const covered = versions.links.filter(
  (edge) => edge.target === test.id && edge.relation === "covered by",
);
assert.deepEqual(
  covered.map((edge) => edge.source),
  ["requirement:example-requirement"],
);
assert(
  !versions.links.some(
    (edge) => edge.source === "requirement:new-version" && edge.target === test.id,
  ),
);

snapshot.suites.push({ ...snapshot.suites[0], id: "another-suite" });
assert.equal(build(snapshot).nodes.filter((node) => node.kind === "test").length, 2);
snapshot.requirements.push({
  ...snapshot.requirements[0],
  id: "another-project",
  project: "Other project",
});
const scoped = build(snapshot, "Other project");
assert.equal(scoped.nodes.length, 2);
assert.equal(scoped.links.length, 1);
assert(
  scoped.nodes.every((node) => node.kind === "project" || node.fields.project === "Other project"),
);

snapshot.attempts.push({
  ...snapshot.attempts[0],
  id: "retest",
  status: "passed",
  retest_of: "example-result",
});
assert(
  build(snapshot).links.some(
    (edge) =>
      edge.source === "result:example-result" &&
      edge.target === "result:retest" &&
      edge.relation === "retested by",
  ),
);
snapshot.defects.push({ ...snapshot.defects[0], id: "orphan", attempt_id: "missing" });
assert(!build(snapshot).nodes.some((node) => node.id === "defect:orphan"));
console.log(
  "Graph relationships, pinned versions, project isolation, case identity and retests passed.",
);

const hierarchy = forest(initial.nodes, initial.links);
assert.equal(hierarchy.placements.size, initial.nodes.length);
assert.equal(hierarchy.edges.length, initial.nodes.length - 1);
assert.equal(new Set(hierarchy.edges.map((edge) => edge.target)).size, hierarchy.edges.length);
const cyclic = forest(
  [{ id: "a" }, { id: "b" }, { id: "orphan" }],
  [
    { source: "a", target: "b" },
    { source: "b", target: "a" },
  ],
);
assert.equal(cyclic.placements.size, 3);
assert.equal(cyclic.edges.length, 1);
assert.equal(forest([], []).placements.size, 0);
const document = markdown([{ id: "unsafe", kind: "requirement", label: '"<img>\nflowchart' }], []);
assert(document.includes("&#34;&#60;img&#62; flowchart"));
assert(!document.includes("<img>"));
assert(markdown(initial.nodes, hierarchy.edges, true).includes("flowchart TD"));
console.log("Tree handles cross-links, cycles and orphan records; Markdown escapes stored labels.");

const domainSnapshot = JSON.parse(JSON.stringify(example));
domainSnapshot.finance_domain = {
  version: "1",
  market: "unspecified",
  currency: "GBP",
  products: [{ id: "HP", name: "Hire Purchase", focus: [] }],
  journeys: [{ id: "quotation", name: "Quotation", focus: [] }],
  rules: [
    {
      id: "BR-TEST",
      version: "1",
      status: "approved",
      description: "Synthetic test rule",
      owner: "Test owner",
      source: "Unit fixture",
      product_ids: ["HP"],
      journey_ids: ["quotation"],
    },
  ],
  mappings: [
    {
      project: "Example project",
      requirement_key: "REQ-001",
      requirement_version: 1,
      product_id: "HP",
      journey_ids: ["quotation"],
      rule_ids: ["BR-TEST"],
    },
  ],
};
domainSnapshot.baselines[0].requirements[0].version = 1;
domainSnapshot.suites[0].suite.test_cases[0].acceptance_criteria_covered = ["BR-TEST"];
let domainGraph = build(domainSnapshot);
assert(
  domainGraph.links.some(
    (edge) => edge.source === "product:HP" && edge.target === "requirement:example-requirement",
  ),
);
assert(
  domainGraph.links.some(
    (edge) => edge.source === "rule:BR-TEST/1" && edge.relation === "explicit coverage",
  ),
);
domainSnapshot.finance_domain.mappings[0].requirement_version = 2;
domainGraph = build(domainSnapshot);
assert(
  !domainGraph.links.some(
    (edge) => edge.source === "product:HP" && edge.target === "requirement:example-requirement",
  ),
);
assert(!domainGraph.links.some((edge) => edge.relation === "explicit coverage"));
domainSnapshot.finance_domain.mappings[0].requirement_version = 1;
domainSnapshot.finance_domain.rules[0].status = "draft";
assert(!build(domainSnapshot).links.some((edge) => edge.relation === "explicit coverage"));
console.log("Domain graph uses explicit approved rules and pinned requirement versions.");
