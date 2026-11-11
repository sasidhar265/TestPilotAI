document.addEventListener("DOMContentLoaded", async () => {
  const form = document.getElementById("appearance-form");
  const fields = document.getElementById("appearance-fields");
  const status = document.getElementById("settings-status");
  const access = document.getElementById("settings-access");
  const rows = document.getElementById("navigation-settings");
  let saved;
  let logo = "";
  let logoSelection = 0;
  let pendingLogo = Promise.resolve(true);
  let admin = false;
  const frame = document.getElementById("main-screen-preview");
  const screen = document.getElementById("preview-screen");
  let previewReady = false;
  let draftTheme = window.workspaceTheme.get();
  function draftSettings() {
    const navigation = { ...saved?.navigation };
    for (const row of rows.querySelectorAll("tr[data-key]"))
      navigation[row.dataset.key] = {
        label: row.querySelector('[data-field="label"]').value.trim(),
        icon: row.querySelector('[data-field="icon"]').value.trim(),
      };
    return {
      title: form.elements.title.value.trim(),
      subtitle: form.elements.subtitle.value.trim(),
      logo,
      background: document.getElementById("default-background").checked
        ? ""
        : form.elements.background.value,
      font_family: form.elements.font_family.value,
      font_size: Number(form.elements.font_size.value) || 16,
      navigation,
    };
  }
  function updatePreview() {
    if (!previewReady || !saved) return;
    // Only the embedded main screen receives draft settings. Nothing is saved here.
    frame.contentWindow.workspaceAppearance.apply(draftSettings());
    frame.contentWindow.workspaceTheme?.preview(draftTheme);
  }
  function resizePreview() {
    const shell = document.getElementById("appearance-preview");
    const scale = shell.clientWidth / 1280;
    frame.style.transform = `scale(${scale})`;
    shell.style.height = `${800 * scale}px`;
  }
  new ResizeObserver(resizePreview).observe(document.getElementById("appearance-preview"));
  function loadPreview() {
    previewReady = false;
    document.getElementById("preview-loading").hidden = false;
    const url = new URL(screen.value, location.origin);
    url.searchParams.set("appearance-preview", "1");
    frame.src = url.pathname + url.search;
    document.getElementById("view-saved-workspace").href = screen.value;
  }
  frame.addEventListener("load", async () => {
    const message = document.getElementById("preview-loading");
    try {
      const ready = frame.contentWindow.appearanceReady;
      if (!ready) throw new Error();
      await ready;
      previewReady = true;
      message.hidden = true;
      updatePreview();
      resizePreview();
    } catch {
      message.textContent = "The main screen preview could not load. Select a screen to retry.";
      message.hidden = false;
    }
  });
  screen.addEventListener("change", loadPreview);
  window.addEventListener("workspace-domain-changed", loadPreview);
  document.querySelectorAll("[data-theme-option]").forEach((button) => {
    button.addEventListener("click", () => {
      draftTheme = button.dataset.themeOption;
      document.querySelectorAll("[data-theme-option]").forEach((option) => {
        const selected = option.dataset.themeOption === draftTheme;
        option.classList.toggle("active", selected);
        option.setAttribute("aria-pressed", String(selected));
      });
      document.getElementById("theme-save-status").textContent =
        "Theme preview updated. Save to apply it to your workspace.";
      updatePreview();
    });
  });
  window.addEventListener("workspace-theme-changed", (event) => {
    draftTheme = event.detail;
    document.getElementById("theme-save-status").textContent = "Theme saved for this browser.";
    updatePreview();
  });
  function saveTheme() {
    const success = window.workspaceTheme.save(draftTheme);
    document.getElementById("theme-save-status").textContent = success
      ? "Theme saved for this browser."
      : "Theme could not be saved. Check browser storage and try again.";
    return success;
  }
  document.getElementById("save-personal-theme").addEventListener("click", saveTheme);

  const previewDialog = document.getElementById("preview-dialog");
  const expandButton = document.getElementById("expand-preview");
  expandButton.addEventListener("click", () => {
    previewDialog.close();
    previewDialog.setAttribute("role", "dialog");
    previewDialog.showModal();
    document.documentElement.classList.add("preview-overlay-open");
    expandButton.setAttribute("aria-expanded", "true");
    document.getElementById("close-preview").focus();
    resizePreview();
  });
  previewDialog.addEventListener("close", () => {
    // Opening the modal also closes its compact presentation first.
    if (previewDialog.matches(":modal")) return;
    previewDialog.setAttribute("role", "region");
    previewDialog.show();
    document.documentElement.classList.remove("preview-overlay-open");
    expandButton.setAttribute("aria-expanded", "false");
    expandButton.focus();
    resizePreview();
  });
  document.getElementById("close-preview").addEventListener("click", () => previewDialog.close());
  previewDialog.addEventListener("click", (event) => {
    if (!previewDialog.matches(":modal") || event.target !== previewDialog) return;
    const bounds = previewDialog.getBoundingClientRect();
    if (
      event.clientX < bounds.left ||
      event.clientX > bounds.right ||
      event.clientY < bounds.top ||
      event.clientY > bounds.bottom
    )
      previewDialog.close();
  });
  form.addEventListener(
    "invalid",
    (event) => {
      const group = event.target.closest("details");
      if (group) group.open = true;
    },
    true,
  );
  form.addEventListener("input", updatePreview);
  form.addEventListener("change", updatePreview);
  function showLogo() {
    const image = document.getElementById("logo-preview");
    image.hidden = !logo;
    if (logo) image.src = logo;
    else image.removeAttribute("src");
    updatePreview();
  }
  function populate(settings) {
    saved = settings;
    for (const key of ["title", "subtitle", "font_family", "font_size"])
      form.elements[key].value = settings[key];
    form.elements.background.value = settings.background || "#f5f6fa";
    document.getElementById("default-background").checked = !settings.background;
    logo = settings.logo;
    showLogo();
    const expanded = new Map(
      [...rows.querySelectorAll("details[data-group]")].map((group) => [
        group.dataset.group,
        group.open,
      ]),
    );
    rows.replaceChildren();
    const groups = new Map();
    const groupNames = {
      sections: "Section headings",
      work: "Workspace controls",
      "workspace-agents": "Agents",
      "workspace-quality-engineering": "Quality Engineering",
      "workspace-data": "Data",
      "workspace-delivery": "Delivery & Operations",
      "workspace-ai-assure": "AI Assure",
      "workspace-administration": "Administration",
      "knowledge-navigation": "Knowledge",
      "finance-navigation": "Auto finance",
      "help-navigation": "Help & diagnostics",
      "admin-navigation": "Admin actions",
    };
    for (const item of window.workspaceAppearance.navigation()) {
      if (!groups.has(item.group)) groups.set(item.group, []);
      groups.get(item.group).push(item);
    }
    for (const [group, items] of groups) {
      const disclosure = document.createElement("details");
      disclosure.className = "settings-nav-group";
      disclosure.dataset.group = group;
      disclosure.open = expanded.get(group) ?? group === "work";
      const summary = document.createElement("summary");
      const name = document.createElement("span");
      name.textContent = groupNames[group] || "Other navigation";
      const count = document.createElement("span");
      count.className = "settings-nav-count";
      count.textContent = `${items.length} items`;
      summary.append(name, count);
      const scroll = document.createElement("div");
      scroll.className = "settings-nav-scroll";
      const table = document.createElement("table");
      table.className = "settings-nav-table";
      const header = document.createElement("thead");
      const headings = document.createElement("tr");
      for (const label of ["Navigation item", "Display label", "Icon"]) {
        const heading = document.createElement("th");
        heading.scope = "col";
        heading.textContent = label;
        headings.append(heading);
      }
      header.append(headings);
      const body = document.createElement("tbody");
      for (const item of items) {
        const tr = document.createElement("tr");
        tr.dataset.key = item.key;
        const original = document.createElement("td");
        original.textContent = item.label;
        tr.append(original);
        for (const key of ["label", "icon"]) {
          const td = document.createElement("td");
          const input = document.createElement("input");
          input.dataset.field = key;
          input.value = (settings.navigation[item.key] || item)[key];
          input.maxLength = key === "label" ? 60 : 8;
          input.required = key === "label";
          input.setAttribute("aria-label", `${item.label} ${key}`);
          td.append(input);
          tr.append(td);
        }
        body.append(tr);
      }
      table.append(header, body);
      scroll.append(table);
      disclosure.append(summary, scroll);
      rows.append(disclosure);
    }
    updatePreview();
  }
  try {
    const [settings, profile] = await Promise.all([
      window.appearanceReady,
      window.loadWorkspaceProfile(),
    ]);
    admin = Boolean(profile.is_admin);
    populate(settings);
    fields.disabled = !admin;
    loadPreview();
    access.textContent = admin
      ? "Shared settings • Changes apply to everyone. Save to publish your updates."
      : "Shared settings • Only administrators can update application branding.";
  } catch {
    access.textContent = "Settings could not be loaded. Reload the page to retry.";
  }
  async function readLogo(file) {
    if (file.size > 500 * 1024)
      throw new Error("Logo must be no larger than 500 KB. Choose a smaller image.");
    // Some file pickers omit MIME types or return image/jpg. Verify the image bytes instead.
    const bytes = new Uint8Array(await file.slice(0, 12).arrayBuffer());
    const matches = (values, offset = 0) => values.every((value, index) => bytes[index + offset] === value);
    const mime = matches([137, 80, 78, 71, 13, 10, 26, 10])
      ? "image/png"
      : matches([255, 216, 255])
        ? "image/jpeg"
        : matches([82, 73, 70, 70]) && matches([87, 69, 66, 80], 8)
          ? "image/webp"
          : null;
    if (!mime) throw new Error("Choose a PNG, JPEG or WebP image. Other image formats are not supported.");
    const encoded = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1]);
      reader.onerror = () => reject(new Error("The logo file could not be read. Select it again."));
      reader.readAsDataURL(file);
    });
    const nextLogo = `data:${mime};base64,${encoded}`;
    const image = new Image();
    image.src = nextLogo;
    try {
      await image.decode();
    } catch {
      throw new Error("This image could not be opened. Export it as PNG, JPEG or WebP and try again.");
    }
    if (Math.max(image.width, image.height) > 2048)
      throw new Error(`Logo is ${image.width} × ${image.height} pixels. Resize it to at most 2048 × 2048 pixels and try again.`);
    return nextLogo;
  }
  document.getElementById("settings-logo").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const selection = ++logoSelection;
    status.textContent = "Reading logo…";
    pendingLogo = (async () => {
      try {
        const nextLogo = await readLogo(file);
        if (selection !== logoSelection) return false;
        logo = nextLogo;
        showLogo();
        status.textContent = "Logo ready. Save settings to apply it.";
        return true;
      } catch (error) {
        if (selection === logoSelection) {
          status.textContent = error.message;
          event.target.value = "";
        }
        return false;
      }
    })();
  });
  document.getElementById("remove-logo").addEventListener("click", () => {
    ++logoSelection;
    pendingLogo = Promise.resolve(true);
    logo = "";
    document.getElementById("settings-logo").value = "";
    showLogo();
    status.textContent = "Default logo selected. Save settings to apply it.";
  });
  async function saveError(response) {
    try {
      const body = await response.json();
      if (typeof body.detail === "string") return body.detail;
      if (Array.isArray(body.detail)) {
        const messages = body.detail.map((issue) => {
          const field = (issue.loc || []).filter((part) => part !== "body").join(" / ");
          return `${field ? field + ": " : ""}${issue.msg || "Invalid value"}`;
        });
        if (messages.length) return messages.join("; ");
      }
    } catch { /* A proxy or unavailable server may return a non-JSON response. */ }
    return response.status === 413
      ? "The server rejected the upload size. Choose an image no larger than 500 KB."
      : response.status === 401 || response.status === 403
        ? "Your session cannot update branding. Sign in with an administrator account and try again."
        : `The server could not save the settings (HTTP ${response.status}). Please try again.`;
  }
  async function persist(value) {
    fields.disabled = true;
    status.textContent = "Saving settings…";
    try {
      const response = await fetch("/api/admin/appearance", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(value),
      });
      if (!response.ok) throw new Error(await saveError(response));
      const settings = await response.json();
      populate(settings);
      window.workspaceAppearance.publish(settings);
      saveTheme();
      document.getElementById("view-saved-workspace").hidden = false;
      status.textContent =
        "Settings saved and applied. Open the updated workspace to see your changes.";
    } catch (error) {
      status.textContent = `Settings could not be saved. ${error.message || "Check the connection and try again."} Your edits are still here.`;
    } finally {
      fields.disabled = !admin;
    }
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!admin || fields.disabled) return;
    // A quick Save must include the selected file, rather than publishing the previous logo.
    const selection = logoSelection;
    const ready = await pendingLogo;
    if (!ready || selection !== logoSelection || fields.disabled) return;
    await persist(draftSettings());
  });
  document.getElementById("reset-appearance").addEventListener("click", () => {
    if (admin) persist({});
  });
});
