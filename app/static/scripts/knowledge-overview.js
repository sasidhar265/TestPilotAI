(() => {
  if (document.body.dataset.knowledgeView !== "overview") return;
  const $ = (id) => document.getElementById(id);
  const groups = window.workspaceKnowledgeSections;
  const icons = ["◇", "◈", "✦"];
  const itemIcons = ["⌕", "◈", "▤", "⌘", "◇", "◷", "✦", "▧", "✓"];
  let selected = "all";
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  function render() {
    const query = $("knowledge-board-search").value.trim().toLowerCase();
    let count = 0,
      offset = 0;
    const columns = groups.flatMap(([name, description, items], index) => {
      const firstIcon = offset;
      offset += items.length;
      if (selected !== "all" && selected !== name) return [];
      const matches = items
        .map((item, itemIndex) => ({ item, icon: itemIcons[firstIcon + itemIndex] }))
        .filter(({ item }) =>
          `${name} ${description} ${item.join(" ")}`.toLowerCase().includes(query),
        );
      count += matches.length;
      const column = node("section", undefined, "knowledge-board-column");
      column.dataset.knowledgeCategory = name;
      const header = node("div", undefined, "knowledge-board-column-heading");
      const icon = node("span", icons[index], "knowledge-tool-icon");
      icon.setAttribute("aria-hidden", "true");
      const title = node("h3", name);
      title.id = `knowledge-column-${index}`;
      column.setAttribute("aria-labelledby", title.id);
      header.append(icon, title, node("span", String(matches.length), "knowledge-tool-count"));
      column.append(header, node("p", description, "knowledge-board-description"));
      for (const {
        item: [title, href, description],
        icon,
      } of matches) {
        const link = node("a", undefined, "knowledge-tool-card");
        link.href = href;
        link.setAttribute("aria-label", title);
        const mark = node("span", icon, "knowledge-tool-icon");
        mark.setAttribute("aria-hidden", "true");
        const copy = node("span", undefined, "knowledge-tool-copy");
        const kind = href.startsWith("/documentation#") ? "Source guide"
          : href.includes("view=search") ? "Content search"
          : href.includes("view=memory") ? "Saved records" : "Reference view";
        copy.append(node("strong", title), node("span", description), node("small", kind, "knowledge-tool-kind"));
        link.append(mark, copy);
        column.append(link);
      }
      if (!matches.length)
        column.append(node("p", "No matching knowledge tools.", "knowledge-tool-empty"));
      return [column];
    });
    $("knowledge-board").replaceChildren(...columns);
    $("knowledge-board").classList.toggle("is-filtered", selected !== "all");
    $("knowledge-board-status").textContent =
      `${count} of ${groups.reduce((sum, [, , items]) => sum + items.length, 0)} knowledge tools`;
    $("knowledge-board-filters")
      .querySelectorAll("button")
      .forEach((button) =>
        button.setAttribute("aria-pressed", String(button.dataset.filter === selected)),
      );
  }
  for (const name of ["all", ...groups.map(([name]) => name)]) {
    const button = node("button", name === "all" ? "All tools" : name);
    button.type = "button";
    button.dataset.filter = name;
    button.addEventListener("click", () => {
      selected = name;
      render();
    });
    $("knowledge-board-filters").append(button);
  }
  $("knowledge-board-search").addEventListener("input", render);
  $("knowledge-board-search").addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.target.value = "";
      render();
    }
  });
  render();
})();
