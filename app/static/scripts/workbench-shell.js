/* Keyboard-first navigation and record discovery reuse existing routes and project context. */
(() => {
  if (document.body.dataset.guest === "true") return;
  const toolbar = document.querySelector(".topbar .top-actions");
  if (!toolbar) return;
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "secondary command-trigger";
  trigger.textContent = "Search · ⌘/Ctrl K";
  trigger.setAttribute("aria-haspopup", "dialog");
  toolbar.prepend(trigger);
  const inbox = document.createElement("a");
  inbox.className = "button secondary";
  inbox.href = "/project-dashboard?queue=approval";
  inbox.textContent = "Approval inbox";
  toolbar.append(inbox);
  const dialog = document.createElement("dialog");
  dialog.className = "workspace-command";
  dialog.setAttribute("aria-labelledby", "workspace-command-title");
  dialog.innerHTML = `<form method="dialog"><div class="command-heading"><h2 id="workspace-command-title">Search workspace</h2><button class="secondary" aria-label="Close workspace search">Close</button></div></form><label>Find a workspace or current project record<input id="workspace-command-input" type="search" autocomplete="off" placeholder="Requirements, backlog, a record title…"></label><div id="workspace-command-results" class="command-results"></div><p id="workspace-command-status" role="status"></p>`;
  document.body.append(dialog);
  let records = [],
    project = null;
  window.addEventListener("sdlc-records-loaded", (event) => {
    records = event.detail.items;
    project = event.detail.project;
  });
  window.addEventListener("sdlc-project-loaded", () => {
    records = [];
    project = null;
  });
  const destinations = [
    ["SDLC workflow", "/sdlc"],
    ["Project dashboard and approval inbox", "/project-dashboard"],
    ["Requirements", "/sdlc?phase=requirements"],
    ["Business approval", "/sdlc?phase=business-approval"],
    ["Backlog", "/sdlc?phase=backlog"],
    ["Development", "/sdlc?phase=development"],
    ["Quality assurance", "/sdlc?phase=qa"],
    ["Release readiness", "/sdlc?phase=release"],
    ["Deployment", "/sdlc?phase=deployment"],
    ["Project documentation and records", "/sdlc"],
    ["Coverage and traceability", "/quality-lifecycle"],
    ["Execution reports", "/progress"],
    ["Application documentation", "/documentation"],
    ["AI usage", "/usage"],
  ];
  const input = dialog.querySelector("input"),
    results = dialog.querySelector(".command-results");
  function render() {
    const query = input.value.trim().toLowerCase();
    results.replaceChildren();
    const entries = [
      ...destinations
        .filter(([, url]) => !window.roleCanNavigate || window.roleCanNavigate(url))
        .map(([title, url]) => ({
          title,
          run: () => {
            if (window.navigateWorkspace && !["/documentation"].includes(url))
              window.navigateWorkspace(url);
            else location.assign(url);
          },
        })),
      ...records.map((record) => ({
        title: `${record.kind.replaceAll("_", " ")}: ${record.title}`,
        run: () => {
          if (location.pathname !== "/sdlc") window.navigateWorkspace("/sdlc", false);
          if (!window.openProjectRecord?.(record.id)) return;
          document.getElementById("lifecycle-records-summary").parentElement.open = true;
          document.getElementById("record-context").scrollIntoView({ block: "center" });
        },
      })),
    ];
    for (const entry of entries.filter((entry) => entry.title.toLowerCase().includes(query))) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = entry.title;
      button.onclick = () => {
        dialog.close();
        entry.run();
      };
      results.append(button);
    }
    dialog.querySelector("#workspace-command-status").textContent = results.children.length
      ? `${results.children.length} matches${project ? " · " + project.name : " · Open a project to search its records"}`
      : "No matches. Try another title.";
  }
  function open() {
    input.value = "";
    render();
    dialog.showModal();
    input.focus();
  }
  trigger.onclick = open;
  input.oninput = render;
  input.onkeydown = (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      results.querySelector("button")?.focus();
    }
    if (event.key === "Enter") {
      event.preventDefault();
      results.querySelector("button")?.click();
    }
  };
  results.onkeydown = (event) => {
    const buttons = [...results.children],
      index = buttons.indexOf(document.activeElement);
    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      buttons[
        (index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length
      ]?.focus();
    }
  };
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (!dialog.open) open();
      else dialog.close();
    }
  });
})();
