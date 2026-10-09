(() => {
  if (document.body.dataset.knowledgeView && !["domain", "calculations"].includes(document.body.dataset.knowledgeView)) return;
  const $ = (id) => document.getElementById(id);
  let currentCalculation = null;
  const fields = {
    annuity: [
      ["principal", "Amount financed"],
      ["annual_nominal_rate", "Annual nominal interest rate (%)"],
      ["payments", "Number of monthly payments"],
      ["balloon", "Balloon paid with last instalment", true],
      ["deposit", "Deposit", true],
      ["upfront_fees", "Upfront fees (not financed)", true],
    ],
    principal: [
      ["cash_price", "Cash price"],
      ["deposit", "Deposit"],
      ["financed_fees", "Financed fees", true],
    ],
    vat: [
      ["net", "Net amount"],
      ["vat_rate", "Supplied VAT rate (%)"],
    ],
  };
  const observedFields = { annuity: "regular_payment", principal: "amount_financed", vat: "gross" };
  function inputs() {
    $("finance-calc-inputs").replaceChildren();
    fields[$("finance-calc-kind").value].forEach(([key, name, optional]) => {
      const label = document.createElement("label"),
        input = document.createElement("input");
      label.textContent = name;
      input.id = `finance-input-${key}`;
      input.type = "text";
      input.inputMode = key === "payments" ? "numeric" : "decimal";
      input.required = !optional;
      if (optional) input.value = "0";
      label.append(input);
      $("finance-calc-inputs").append(label);
    });
    $("finance-observed-help").textContent =
      `Observed field: ${observedFields[$("finance-calc-kind").value].replaceAll("_", " ")}. Comparison is exact at the configured currency precision.`;
    currentCalculation = null;
    $("finance-calc-result").hidden = true;
    $("finance-calc-status").textContent = "";
    $("finance-observed").value = "";
  }
  $("finance-calc-kind").addEventListener("change", inputs);
  inputs();
  fetch("/api/finance/domain-pack", { credentials: "same-origin", cache: "no-store" })
    .then((response) => {
      if (!response.ok)
        throw new Error(
          "Domain configuration unavailable. Check the runtime config and domain pack.",
        );
      return response.json();
    })
    .then((pack) => {
      $("finance-pack-status").textContent =
        `Pack v${pack.version} · market: ${pack.market} · ${pack.currency}, ${pack.minor_units} decimal places, ${pack.rounding.replaceAll("_", " ")} rounding · ${pack.rules.filter((r) => r.status === "approved").length} approved rules. Products and journey focus are reference-only.`;
      [
        ["products", "finance-products"],
        ["journeys", "finance-journeys"],
      ].forEach(([key, target]) =>
        pack[key].forEach((item) => {
          const li = document.createElement("li"),
            name = document.createElement("strong"),
            focus = document.createElement("span");
          name.textContent = `${item.id} · ${item.name}`;
          focus.textContent = item.focus.join(" · ");
          li.append(name, focus);
          $(target).append(li);
        }),
      );
      if (!pack.rules.length)
        $("finance-rules").textContent =
          "No approved domain rules supplied. Reference focus must not be promoted into business policy.";
      pack.rules.forEach((rule) => {
        const p = document.createElement("p");
        p.textContent = `${rule.id} v${rule.version} · ${rule.status} · ${rule.description} · owner: ${rule.owner} · source: ${rule.source}`;
        $("finance-rules").append(p);
      });
    })
    .catch((error) => {
      $("finance-pack-status").textContent = error.message;
      $("finance-calculate").disabled = true;
    });
  $("finance-calc-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const kind = $("finance-calc-kind").value,
      payload = { kind, observed: {} };
    fields[kind].forEach(([key]) => {
      payload[key] = $("finance-input-" + key).value.trim();
    });
    if ($("finance-observed").value.trim())
      payload.observed[observedFields[kind]] = $("finance-observed").value.trim();
    $("finance-calculate").disabled = true;
    currentCalculation = null;
    $("finance-calc-result").hidden = true;
    $("finance-calc-status").textContent = "Calculating with Decimal arithmetic…";
    try {
      const response = await fetch("/api/finance/calculations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Invalid inputs. Check amounts, rate, payment count and currency precision.",
        );
      $("finance-calc-values").replaceChildren();
      $("finance-calc-checks").replaceChildren();
      Object.entries(result.result).forEach(([key, value]) => {
        const term = document.createElement("dt"),
          amount = document.createElement("dd");
        term.textContent = key.replaceAll("_", " ");
        amount.textContent = `${result.currency} ${value}`;
        $("finance-calc-values").append(term, amount);
      });
      result.checks.forEach((check) => {
        const li = document.createElement("li");
        li.textContent = `${check.field}: ${check.passed ? "matches" : "mismatch"} · expected ${check.expected} · observed ${check.observed} · difference ${check.difference}`;
        $("finance-calc-checks").append(li);
      });
      $("finance-calc-status").textContent =
        result.matches_observed === null
          ? "Calculated reference values. No observed value supplied."
          : result.matches_observed
            ? "Observed value matches."
            : "Observed value does not match.";
      $("finance-calc-convention").textContent = result.convention;
      $("finance-calc-scope").textContent = result.scope;
      currentCalculation = payload;
      $("finance-calc-result").hidden = false;
    } catch (error) {
      $("finance-calc-status").textContent = error.message;
    } finally {
      $("finance-calculate").disabled = false;
    }
  });
  $("finance-use-calculation").addEventListener("click", () => {
    if (!currentCalculation) return;
    try {
      sessionStorage.setItem("finance-reference-calculation", JSON.stringify(currentCalculation));
      window.location.href = "/#test-studio";
    } catch {
      $("finance-calc-status").textContent =
        "Browser storage is unavailable. Copy the reference values into your approved requirement context.";
    }
  });
})();
