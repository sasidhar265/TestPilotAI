(() => {
  const node = (tag, text, cls) => {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (cls) element.className = cls;
    return element;
  };
  // Render a bounded Markdown subset using DOM nodes only. Source HTML stays inert.
  const inline = (element, text) => {
    const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|https?:\/\/[^\s]+)/g;
    let offset = 0;
    for (const match of text.matchAll(pattern)) {
      element.append(document.createTextNode(text.slice(offset, match.index)));
      const value = match[0];
      if (value.startsWith("`")) element.append(node("code", value.slice(1, -1)));
      else if (value.startsWith("**")) element.append(node("strong", value.slice(2, -2)));
      else {
        const parts = /^\[([^\]]+)\]\((.+)\)$/.exec(value);
        const link = node("a", parts ? parts[1] : value);
        link.href = parts ? parts[2] : value;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        element.append(link);
      }
      offset = match.index + value.length;
    }
    element.append(document.createTextNode(text.slice(offset)));
  };
  const renderDocument = (content, target) => {
    const lines = content.split("\n");
    let i = 0;
    while (i < lines.length) {
      const line = lines[i].trim();
      if (!line || /^# /.test(line) || /^(Version|Status|Owner|Reviewed|Scope|Authority):/.test(line)) { i++; continue; }
      if (/^#{2,4} /.test(line)) {
        const heading = node("h3");
        inline(heading, line.replace(/^#+ /, ""));
        target.append(heading); i++; continue;
      }
      if (line.startsWith("|")) {
        const wrap = node("div", "", "library-table");
        const table = node("table");
        let rowIndex = 0;
        while (i < lines.length && lines[i].trim().startsWith("|")) {
          const cells = lines[i++].trim().replace(/^\||\|$/g, "").split("|");
          if (cells.every((value) => /^[\s:-]+$/.test(value))) continue;
          const row = node("tr");
          cells.forEach((value) => {
            const cell = node(rowIndex === 0 ? "th" : "td");
            inline(cell, value.trim()); row.append(cell);
          });
          table.append(row); rowIndex++;
        }
        wrap.append(table); target.append(wrap); continue;
      }
      if (/^([-*] |\d+\. )/.test(line)) {
        const list = node(/^\d/.test(line) ? "ol" : "ul");
        while (i < lines.length && /^([-*] |\d+\. )/.test(lines[i].trim())) {
          let value = lines[i++].trim().replace(/^([-*] |\d+\. )/, "");
          while (i < lines.length && /^\s+\S/.test(lines[i])) value += " " + lines[i++].trim();
          const item = node("li"); inline(item, value); list.append(item);
        }
        target.append(list); continue;
      }
      let paragraph = lines[i++].trim();
      while (i < lines.length && lines[i].trim() && !/^(#|\||[-*] |\d+\. )/.test(lines[i].trim())) paragraph += " " + lines[i++].trim();
      const p = node("p"); inline(p, paragraph); target.append(p);
    }
  };
  window.renderKnowledgeDocument = renderDocument;
})();
