/* Native test scripts retain explicit inputs and the selected suite snapshot. */
(() => {
  let snapshot = null,
    cases = [],
    artifact = null,
    packRequest = null,
    revision = 0;
  const dialog = $("script-pack-dialog");
  const invalidate = () => {
    revision++;
    artifact = null;
    packRequest = null;
    $("script-pack-preview").hidden = true;
    $("script-pack-status").textContent = "";
  };
  window.resetScriptPack = () => {
    invalidate();
    dialog.close();
    snapshot = null;
  };
  function mappings() {
    invalidate();
    const browser = $("script-pack-target").value === "browser";
    const performance = ["jmeter", "browser"].includes($("script-pack-target").value);
    $("script-load-settings").hidden = !performance;
    $("script-performance-budgets").hidden = !performance;
    $("script-duration").disabled = browser;
    $("script-pack-help").textContent = browser
      ? "Supply the real page path, ready selector and optional journey actions. Browser users measure navigation plus actions to readiness. Use environment variable names for secret inputs."
      : performance
      ? "Supply the approved request and response-time budget for each case. Configure the target host in the downloaded pack."
      : "Supply the SELECT query for each case and the expected number of returned rows. For data-quality checks, return violating rows and expect zero. Use your actual schema names.";
    $("script-case-mappings").innerHTML = cases
      .map((item, index) => {
        const data = Object.fromEntries(item.test_data.map((d) => [d.name.toLowerCase(), d.value]));
        const input = (name, label, type = "text", value = "", extra = "") =>
          `<label>${label}<input data-field="${name}" type="${type}" value="${esc(value)}" ${extra} /></label>`;
        const textarea = (name, label, value = "", extra = "") =>
          `<label>${label}<textarea data-field="${name}" rows="3" ${extra}>${esc(value)}</textarea></label>`;
        return `<fieldset data-script-case="${index}"><legend>${esc(item.id)} · ${esc(item.title)}</legend>${
          browser
            ? `${input("path", "Page path", "text", data.path || "", 'required placeholder="/your-page"')}${input("ready_selector", "Journey ready selector", "text", data.ready_selector || "", 'required placeholder="Your verified CSS or Playwright selector"')}${input("expected_status", "Expected navigation status", "number", data.expected_status || "200", 'required min="100" max="599"')}${input("max_response_ms", "Maximum journey time (ms)", "number", data.max_response_ms || "", 'required min="1" max="3600000"')}${textarea("actions", "Actions (JSON array: click, fill, select, wait_visible)", data.actions || "[]")}<p class="field-help">Each action supplies action and selector; fill/select may include value. Secret fill values use value_env. Readiness selectors and actions must match your application.</p>`
            : performance
            ? `<div class="script-load-settings"><label>HTTP method<select data-field="method">${["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"].map((method) => `<option${method === data.method ? " selected" : ""}>${method}</option>`).join("")}</select></label>${input("path", "Request path", "text", data.path || "", 'required placeholder="/your-endpoint"')}${input("expected_status", "Expected HTTP status", "number", data.expected_status || "", 'required min="100" max="599"')}</div>${input("max_response_ms", "Maximum response time (ms)", "number", data.max_response_ms || "", 'required min="1" max="3600000"')}${textarea("body", "Approved request body (optional)", data.request_body || "")}${input("content_type", "Content type", "text", data.content_type || "application/json", "required")}<details><summary>Request headers</summary><p>JSON object of header names and values. Use JMeter property references for runtime credentials.</p>${textarea("headers", "Headers (JSON)", "{}")}</details>`
            : `${textarea("query", "SELECT query", data.query || "", "required")}${input("expected_rows", "Expected returned rows", "number", data.expected_rows || "", 'required min="0" max="2147483647"')}`
        }</fieldset>`;
      })
      .join("");
  }
  $("open-script-pack").onclick = () => {
    try {
      requireApprovedSuite();
      const selected = new Set(selectedCaseIds());
      if (!selected.size) throw new Error("Select the test cases to include in the script pack.");
      snapshot = suite;
      cases = suite.test_cases.filter((item) => selected.has(item.id));
      $("script-pack-scope").textContent =
        `${cases.length} selected test case${cases.length === 1 ? "" : "s"} · ${suite.feature_name}`;
      mappings();
      dialog.showModal();
    } catch (error) {
      $("status").textContent = error.message;
    }
  };
  $("close-script-pack").onclick = () => dialog.close();
  $("script-pack-target").onchange = mappings;
  $("script-pack-form").addEventListener("input", invalidate);
  $("script-pack-form").onsubmit = async (event) => {
    event.preventDefault();
    invalidate();
    const version = revision;
    try {
      requireApprovedSuite();
      if (suite !== snapshot) throw new Error("The suite changed. Reopen the script builder.");
      const target = $("script-pack-target").value;
      const rows = [...document.querySelectorAll("[data-script-case]")].map((row, index) => {
        const result = { case_id: cases[index].id };
        row.querySelectorAll("[data-field]").forEach((input) => {
          result[input.dataset.field] = input.type === "number" ? Number(input.value) : input.value;
        });
        if (target === "jmeter") result.headers = JSON.parse(result.headers || "{}");
        if (target === "browser") result.actions = JSON.parse(result.actions || "[]");
        return result;
      });
      const request = {
        suite: { ...snapshot, test_cases: cases },
        validation: validationReport,
        target,
        threads: Number($("script-threads").value),
        ramp_seconds: Number($("script-ramp").value),
        iterations: Number($("script-iterations").value),
        think_time_ms: Number($("script-think-time").value),
        warmup_seconds: Number($("script-warmup").value),
        duration_seconds: target === "jmeter" ? Number($("script-duration").value) : 0,
        p95_ms: $("script-p95").value ? Number($("script-p95").value) : null,
        p99_ms: $("script-p99").value ? Number($("script-p99").value) : null,
        max_error_percent: Number($("script-error-rate").value),
        min_samples: Number($("script-min-samples").value),
        [target === "jmeter" ? "http_checks" : target === "browser" ? "browser_checks" : "database_checks"]: rows,
      };
      $("generate-script-pack").disabled = true;
      $("script-pack-status").textContent = "Building script pack…";
      const response = await api("/api/script-packs/generate", request);
      const result = await response.json();
      if (version !== revision || suite !== snapshot) return;
      artifact = result;
      packRequest = request;
      $("script-pack-file").innerHTML = result.files
        .map((file, index) => `<option value="${index}">${esc(file.path)}</option>`)
        .join("");
      $("script-pack-file").value = String(
        result.files.findIndex((file) => file.path.startsWith("Features/")),
      );
      $("script-pack-file").onchange();
      $("script-pack-preview").hidden = false;
      $("script-pack-status").textContent =
        `${result.case_ids.length} cases mapped. Scripts ready for review; not executed.`;
    } catch (error) {
      if (version === revision) $("script-pack-status").textContent = error.message;
    } finally {
      $("generate-script-pack").disabled = false;
    }
  };
  $("script-pack-file").onchange = () => {
    $("script-pack-content").textContent =
      artifact?.files[Number($("script-pack-file").value)]?.content || "";
  };
  $("download-script-pack").onclick = async () => {
    const version = revision,
      request = packRequest;
    if (!request || suite !== snapshot) return;
    try {
      const response = await api("/api/script-packs/download", request);
      const blob = await response.blob();
      if (version === revision && suite === snapshot)
        download(blob, `${request.target}-test-pack.zip`);
    } catch (error) {
      $("script-pack-status").textContent = error.message;
    }
  };
})();
