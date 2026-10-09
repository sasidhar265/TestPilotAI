(() => {
  if (document.body.dataset.knowledgeView && document.body.dataset.knowledgeView !== "graph") return;
  const $ = (id) => document.getElementById(id);
  const data = window.KnowledgeGraphData;
  const colors = [
    "#6366f1",
    "#0284c7",
    "#0891b2",
    "#8b5cf6",
    "#d97706",
    "#059669",
    "#db2777",
    "#e05252",
    "#334155",
    "#0d9488",
    "#7c3aed",
    "#b45309",
  ];
  const ns = "http://www.w3.org/2000/svg";
  let live = {},
    graph = { nodes: [], links: [] },
    positions = new Map(),
    selected = "",
    zoom = 1,
    view = "graph",
    dragging = null,
    suppressClick = false;
  let width = 1000,
    height = 440,
    request = 0,
    loaded = false,
    initial = true;
  const make = (tag, attrs = {}, value) => {
    const node = document.createElementNS(ns, tag);
    Object.entries(attrs).forEach(([key, item]) => node.setAttribute(key, item));
    if (value !== undefined) node.textContent = value;
    return node;
  };
  const label = (kind) => (kind === "test" ? "Test case" : kind[0].toUpperCase() + kind.slice(1));
  const crop = (text, length = 22) =>
    String(text).length > length ? String(text).slice(0, length - 1) + "…" : text;
  data.types.forEach((kind, index) => {
    $("graph-kind").add(new Option(label(kind), kind));
    const item = document.createElement("span"),
      dot = document.createElement("i");
    dot.style.background = colors[index];
    item.append(dot, document.createTextNode(label(kind)));
    $("graph-legend").append(item);
  });
  function size() {
    $("knowledge-graph").setAttribute("width", width * zoom);
    $("knowledge-graph").setAttribute("height", height * zoom);
    $("graph-zoom-level").textContent = `${Math.round(zoom * 100)}%`;
  }
  function fit() {
    zoom = Math.max(
      0.2,
      Math.min(1, $("graph-canvas").clientWidth / width, $("graph-canvas").clientHeight / height),
    );
    size();
    $("graph-canvas").scrollTo(0, 0);
  }
  function inspect(identifier) {
    const node = graph.nodes.find((item) => item.id === identifier);
    if (!node) return;
    selected = identifier;
    $("graph-detail-title").textContent = node.label;
    $("graph-detail-description").textContent =
      `${label(node.kind)}${$("graph-source").value === "example" ? " · illustrative example" : " · stored record"}`;
    $("graph-detail-fields").replaceChildren();
    Object.entries(node.fields)
      .filter(([, value]) => value !== undefined && value !== null && value !== "")
      .forEach(([key, value]) => {
        const term = document.createElement("dt"),
          description = document.createElement("dd");
        term.textContent = key;
        description.textContent = value;
        $("graph-detail-fields").append(term, description);
      });
    const neighbors = new Set([identifier]);
    $("graph-detail-links").replaceChildren();
    graph.links
      .filter((edge) => edge.source === identifier || edge.target === identifier)
      .forEach((edge) => {
        const otherId = edge.source === identifier ? edge.target : edge.source;
        neighbors.add(otherId);
        const other = graph.nodes.find((item) => item.id === otherId);
        const item = document.createElement("li"),
          button = document.createElement("button");
        button.type = "button";
        button.textContent = other.label;
        button.addEventListener("click", () => {
          inspect(otherId);
          const element = [...document.querySelectorAll(".graph-node")].find(
            (entry) => entry.dataset.id === otherId,
          );
          element?.scrollIntoView({ block: "nearest", inline: "nearest" });
          element?.focus();
        });
        item.append(
          document.createTextNode(`${edge.source === identifier ? "→" : "←"} ${edge.relation}: `),
          button,
        );
        $("graph-detail-links").append(item);
      });
    document.querySelectorAll(".graph-node").forEach((element) => {
      element.classList.toggle("is-selected", element.dataset.id === identifier);
      element.classList.toggle("is-muted", !neighbors.has(element.dataset.id));
      element.setAttribute("aria-pressed", element.dataset.id === identifier);
    });
    document.querySelectorAll(".graph-edge").forEach((element) => {
      const active = element.dataset.source === identifier || element.dataset.target === identifier;
      element.classList.toggle("is-selected", active);
      element.classList.toggle("is-muted", !active);
    });
  }
  function render(reset = true) {
    const example = $("graph-source").value === "example";
    graph = data.build(example ? data.example : live, $("graph-project").value);
    const query = $("graph-search").value.toLowerCase().trim(),
      kind = $("graph-kind").value;
    const matches = new Set(
      graph.nodes
        .filter(
          (node) =>
            (!kind || node.kind === kind) &&
            (!query ||
              `${node.label} ${Object.values(node.fields).join(" ")}`
                .toLowerCase()
                .includes(query)),
        )
        .map((node) => node.id),
    );
    const included = new Set(matches);
    graph.links.forEach((edge) => {
      if (matches.has(edge.source)) included.add(edge.target);
      if (matches.has(edge.target)) included.add(edge.source);
    });
    const nodes = graph.nodes.filter((node) => included.has(node.id)).slice(0, 300);
    const visible = new Set(nodes.map((node) => node.id));
    let links = graph.links.filter((edge) => visible.has(edge.source) && visible.has(edge.target));
    const svg = $("knowledge-graph");
    svg.replaceChildren();
    positions = new Map();
    const layers = [
      ["project", "domain", "product"],
      ["requirement", "baseline", "journey", "rule"],
      ["suite", "test"],
      ["cycle", "result"],
      ["defect"],
    ];
    const columns = layers.map((types) => nodes.filter((node) => types.includes(node.kind)));
    const present = columns.filter((column) => column.length);
    width = Math.max(600, present.length * 230 + 60);
    height = Math.max(440, ...present.map((column) => column.length * 115 + 90));
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const defs = make("defs"),
      marker = make("marker", {
        id: "graph-arrow",
        viewBox: "0 0 10 10",
        refX: 9,
        refY: 5,
        markerWidth: 6,
        markerHeight: 6,
        orient: "auto-start-reverse",
      });
    marker.append(make("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#9297ad" }));
    defs.append(marker);
    svg.append(defs);
    present.forEach((column, x) =>
      column.forEach((node, y) => positions.set(node.id, { x: 30 + x * 230, y: 40 + y * 115 })),
    );
    if (view === "tree") {
      const tree = data.forest(nodes, links);
      positions = tree.placements;
      links = tree.edges;
      width = Math.max(600, ...[...positions.values()].map((point) => point.x + 220));
      height = Math.max(440, ...[...positions.values()].map((point) => point.y + 120));
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    }
    $("graph-help").textContent =
      view === "tree"
        ? "Hierarchy shows each record once. Additional relationships remain in node details and the Graph tab. Drag nodes to rearrange. Drag the background to pan; use the mouse wheel to zoom. Additional relationships remain in Graph and node details."
        : "Drag nodes to rearrange. Drag the background to pan; use the mouse wheel to zoom. Select a node to highlight its connections. Tab and Enter also select nodes.";
    $("graph-markdown-source").textContent = data.markdown(nodes, links, view === "tree");
    if (view === "graph" && nodes.length <= 40) {
      const root =
        nodes.find((node) => node.kind === "project") ||
        nodes.find((node) => node.kind === "domain") ||
        nodes[0];
      const others = nodes.filter((node) => node !== root);
      const radius = Math.max(240, others.length * 40);
      width = radius * 2 + 360;
      height = radius * 2 + 240;
      const cx = width / 2,
        cy = height / 2;
      if (root) positions.set(root.id, { x: cx - 87, y: cy - 38 });
      others.forEach((node, index) => {
        const angle = -Math.PI / 2 + (index * Math.PI * 2) / others.length;
        positions.set(node.id, {
          x: cx + Math.cos(angle) * radius - 87,
          y: cy + Math.sin(angle) * radius - 38,
        });
      });
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    }
    links.forEach((edge) => {
      const group = make("g", {
        class: "graph-edge",
        tabindex: 0,
        role: "button",
        "aria-label": `${edge.relation}: ${graph.nodes.find((n) => n.id === edge.source).label} to ${graph.nodes.find((n) => n.id === edge.target).label}`,
      });
      group.dataset.source = edge.source;
      group.dataset.target = edge.target;
      group.append(
        make("path", { class: "edge-hit" }),
        make("path", { class: "edge-line", "marker-end": "url(#graph-arrow)" }),
        make("rect", { class: "edge-label-bg", rx: 7 }),
        make("text", { "text-anchor": "middle" }, edge.relation),
        make("title", {}, edge.relation),
      );
      group.addEventListener("click", () => inspect(edge.source));
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          inspect(edge.source);
        }
      });
      svg.append(group);
    });
    nodes.forEach((node) => {
      const point = positions.get(node.id),
        index = data.types.indexOf(node.kind);
      const group = make("g", {
        class: "graph-node",
        transform: `translate(${point.x},${point.y})`,
        tabindex: 0,
        role: "button",
        "aria-label": `${label(node.kind)}: ${node.label}`,
        "aria-pressed": "false",
      });
      group.dataset.id = node.id;
      group.append(
        make("rect", { width: 174, height: 76, rx: 14 }),
        make("rect", {
          class: "node-accent",
          width: 4,
          height: 46,
          x: 0,
          y: 15,
          rx: 2,
          style: `fill:${colors[index]}`,
        }),
        make("circle", { cx: 14, cy: 17, r: 4, fill: colors[index] }),
        make("text", { x: 25, y: 21, class: "node-kind" }, label(node.kind)),
        make("text", { x: 12, y: 43 }, crop(node.label)),
        make(
          "text",
          { x: 12, y: 62, class: "node-status" },
          crop(node.fields.status || node.fields.title || node.fields.environment || "", 26),
        ),
        make("title", {}, `${node.label}\n${node.fields.title || ""}`),
      );
      group.addEventListener("click", () => {
        if (!suppressClick) inspect(node.id);
      });
      group.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        event.stopPropagation();
        suppressClick = false;
        const rect = svg.getBoundingClientRect();
        dragging = {
          node: node.id,
          element: group,
          startX: event.clientX,
          startY: event.clientY,
          x: positions.get(node.id).x,
          y: positions.get(node.id).y,
          scale: width / rect.width,
        };
        group.setPointerCapture(event.pointerId);
        group.classList.add("is-dragging");
      });
      group.addEventListener("keydown", (event) => {
        if (["Enter", " "].includes(event.key)) {
          event.preventDefault();
          inspect(node.id);
        }
      });
      svg.append(group);
    });
    updateEdges();
    $("graph-empty").hidden = nodes.length > 0;
    svg.style.display = nodes.length ? "block" : "none";
    $("graph-empty").textContent = graph.nodes.length
      ? "No matching nodes. Clear the search or change the focus."
      : "No lifecycle records are saved for this source. Explore the Example graph, or create requirements in Test management.";
    $("graph-counts").textContent =
      `${nodes.length} nodes · ${links.length} relationships${included.size > 300 ? " · first 300 nodes shown; narrow the project or search" : ""}`;
    $("graph-status").dataset.example = example;
    $("graph-status").textContent = example
      ? "Example graph · illustrative records only. These are not stored requirements, approved tests or execution evidence. Choose Live records to inspect your project."
      : "Live view · domain catalogue nodes are references. Evidence links require explicit project, requirement-version and test mappings. No coverage is inferred from matching names.";
    if (reset || (selected && !visible.has(selected))) {
      selected = "";
      $("graph-detail-title").textContent = "Select a node";
      $("graph-detail-description").textContent =
        "Select a node to inspect its information and direct connections.";
      $("graph-detail-fields").replaceChildren();
      $("graph-detail-links").replaceChildren();
      fit();
    } else if (selected && visible.has(selected)) inspect(selected);
    size();
  }
  function updateEdges() {
    document.querySelectorAll(".graph-edge").forEach((group) => {
      const from = positions.get(group.dataset.source),
        to = positions.get(group.dataset.target);
      if (!from || !to) return;
      const dx = to.x - from.x,
        dy = to.y - from.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const boundary = Math.min(
        87 / Math.max(0.001, Math.abs(dx / distance)),
        38 / Math.max(0.001, Math.abs(dy / distance)),
      );
      const x1 = from.x + 87 + (dx / distance) * boundary;
      const y1 = from.y + 38 + (dy / distance) * boundary;
      const x2 = to.x + 87 - (dx / distance) * boundary;
      const y2 = to.y + 38 - (dy / distance) * boundary;
      const mx = (x1 + x2) / 2,
        my = (y1 + y2) / 2;
      const path =
        view === "tree"
          ? `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`
          : `M${x1},${y1} Q${mx - dy * 0.12},${my + dx * 0.12} ${x2},${y2}`;
      group.querySelectorAll("path").forEach((element) => element.setAttribute("d", path));
      const tx = view === "tree" ? mx : mx - dy * 0.06;
      const ty = view === "tree" ? my : my + dx * 0.06;
      const text = group.querySelector("text");
      text.setAttribute("x", tx);
      text.setAttribute("y", ty + 3);
      const w = text.textContent.length * 5.8 + 14;
      const bg = group.querySelector("rect");
      Object.entries({ x: tx - w / 2, y: ty - 10, width: w, height: 20 }).forEach(([key, value]) =>
        bg.setAttribute(key, value),
      );
    });
  }
  const canvas = $("graph-canvas");
  canvas.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target.closest(".graph-node, .graph-edge")) return;
    dragging = {
      startX: event.clientX,
      startY: event.clientY,
      left: canvas.scrollLeft,
      top: canvas.scrollTop,
    };
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add("is-panning");
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const dx = event.clientX - dragging.startX,
      dy = event.clientY - dragging.startY;
    if (dragging.node) {
      if (Math.hypot(dx, dy) > 3) suppressClick = true;
      const point = {
        x: Math.max(10, Math.min(width - 184, dragging.x + dx * dragging.scale)),
        y: Math.max(10, Math.min(height - 86, dragging.y + dy * dragging.scale)),
      };
      positions.set(dragging.node, point);
      dragging.element.setAttribute("transform", `translate(${point.x},${point.y})`);
      updateEdges();
    } else {
      canvas.scrollLeft = dragging.left - dx;
      canvas.scrollTop = dragging.top - dy;
    }
  });
  function endDrag() {
    dragging?.element?.classList.remove("is-dragging");
    dragging = null;
    canvas.classList.remove("is-panning");
    setTimeout(() => {
      suppressClick = false;
    }, 0);
  }
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);
  canvas.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left,
        y = event.clientY - rect.top;
      const old = zoom;
      zoom = Math.max(0.2, Math.min(2, zoom * (event.deltaY < 0 ? 1.12 : 1 / 1.12)));
      const left = ((canvas.scrollLeft + x) * zoom) / old - x;
      const top = ((canvas.scrollTop + y) * zoom) / old - y;
      size();
      canvas.scrollTo(left, top);
    },
    { passive: false },
  );
  function projects() {
    const graph = data.build($("graph-source").value === "example" ? data.example : live),
      previous = $("graph-project").value;
    $("graph-project").replaceChildren(
      new Option("All projects", ""),
      ...graph.projects.map((name) => new Option(name, name)),
    );
    if (graph.projects.includes(previous)) $("graph-project").value = previous;
  }
  async function refresh(automatic = false) {
    if (automatic && (document.hidden || dragging || $("graph-refresh").disabled)) return;
    const revision = ++request;
    $("graph-refresh").disabled = true;
    if (!automatic) $("graph-status").textContent = "Loading lifecycle records…";
    try {
      const response = await fetch("/api/stlc", { credentials: "same-origin", cache: "no-store" });
      if (!response.ok) throw new Error("Could not load lifecycle records. Refresh to retry.");
      const correlation = response.headers.get("x-request-id");
      $("graph-log-link").href = correlation
        ? `/logs?request_id=${encodeURIComponent(correlation)}`
        : "/logs";
      const snapshot = await response.json();
      try {
        const domainResponse = await fetch("/api/finance/domain-pack", {
          credentials: "same-origin",
          cache: "no-store",
        });
        if (domainResponse.ok) {
          const domain = await domainResponse.json();
          if (Array.isArray(domain.products) && Array.isArray(domain.journeys))
            snapshot.finance_domain = domain;
        }
      } catch {
        /* Lifecycle evidence remains visible if the domain source is unavailable. */
      }
      if (revision !== request) return;
      const changed = JSON.stringify(live) !== JSON.stringify(snapshot);
      live = snapshot;
      loaded = true;
      if (initial && !data.build(live).nodes.length) $("graph-source").value = "example";
      initial = false;
      if (!automatic || changed) {
        projects();
        render(!automatic);
      }
      $("graph-live-state").textContent =
        `Updated ${new Date().toLocaleTimeString()} · refreshes every 30 seconds`;
    } catch (error) {
      if (revision === request) {
        $("graph-status").dataset.example = "false";
        $("graph-status").textContent = error.message;
        $("graph-counts").textContent = "Source unavailable";
        $("graph-live-state").textContent = "Refresh failed · retrying in 30 seconds";
      }
    } finally {
      if (revision === request) $("graph-refresh").disabled = false;
    }
  }
  $("graph-source").addEventListener("change", () => {
    initial = false;
    if ($("graph-source").value === "live" && !loaded) {
      refresh();
      return;
    }
    projects();
    render();
  });
  ["graph-project", "graph-kind"].forEach((name) =>
    $(name).addEventListener("change", () => render()),
  );
  $("graph-search").addEventListener("input", () => render());
  $("graph-refresh").addEventListener("click", () => refresh());
  const tabs = [$("graph-tab"), $("tree-tab")];
  function activateTab(index) {
    view = index === 0 ? "graph" : "tree";
    tabs.forEach((tab, i) => {
      tab.setAttribute("aria-selected", i === index);
      tab.tabIndex = i === index ? 0 : -1;
    });
    $("graph-panel").setAttribute("aria-labelledby", tabs[index].id);
    render(false);
    fit();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateTab(index));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : 1 - index;
      activateTab(next);
      tabs[next].focus();
    });
  });
  $("graph-download").addEventListener("click", () => {
    const example = $("graph-source").value === "example";
    const markdown = $("graph-markdown-source").textContent.replace(
      "\n\n",
      `\n\n${example ? "Illustrative example only; not stored project records." : "Snapshot of stored lifecycle records."}\n\n`,
    );
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `business-model-${view}${example ? "-example" : ""}.md`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $("graph-reset").addEventListener("click", () => {
    render();
  });
  $("graph-expand").addEventListener("click", () => {
    const expanded = $("graph-workspace").classList.toggle("is-expanded");
    $("graph-expand").textContent = expanded ? "Exit expanded view" : "Expand";
    $("graph-expand").setAttribute("aria-pressed", expanded);
    requestAnimationFrame(fit);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("graph-workspace").classList.contains("is-expanded")) {
      $("graph-expand").click();
      $("graph-expand").focus();
    }
  });
  $("graph-fit").addEventListener("click", fit);
  $("graph-zoom-in").addEventListener("click", () => {
    zoom = Math.min(2, zoom * 1.25);
    size();
  });
  $("graph-zoom-out").addEventListener("click", () => {
    zoom = Math.max(0.2, zoom / 1.25);
    size();
  });
  refresh();
  setInterval(() => refresh(true), 30000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh(true);
  });
})();
