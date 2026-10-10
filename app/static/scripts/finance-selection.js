(() => {
  window.financeCalculationContext = () => {
    try {
      return JSON.parse(sessionStorage.getItem("finance-reference-calculation") || "null");
    } catch {
      return null;
    }
  };
  if (document.body.dataset.guest === "true") return;
  const reference = window.financeCalculationContext();
  if (reference) {
    document.getElementById("finance-reference-status").hidden = false;
    document.getElementById("finance-reference-status").textContent =
      `Reference calculation attached: ${reference.kind}. The server recomputes values from supplied inputs before generation; this does not approve product pricing.`;
    document.getElementById("finance-clear-reference").hidden = false;
  }
  document.getElementById("finance-clear-reference").addEventListener("click", () => {
    try {
      sessionStorage.removeItem("finance-reference-calculation");
    } catch {
      return;
    }
    document.getElementById("finance-reference-status").hidden = true;
    document.getElementById("finance-clear-reference").hidden = true;
    window.dispatchEvent(new Event("workspace-source-replaced"));
  });
  const product = document.getElementById("finance-domain-product");
  const journey = document.getElementById("finance-domain-journey");
  const status = document.getElementById("finance-domain-selection-status");
  fetch("/api/finance/domain-pack", { credentials: "same-origin", cache: "no-store" })
    .then((response) => {
      if (!response.ok)
        throw new Error("Domain context unavailable; use the approved requirement directly.");
      return response.json();
    })
    .then((pack) => {
      pack.products.forEach((item) =>
        product.add(new Option(`${item.id} · ${item.name}`, item.id)),
      );
      pack.journeys.forEach((item) => journey.add(new Option(item.name, item.id)));
      const update = () => {
        const approved = pack.rules.filter(
          (rule) =>
            rule.status === "approved" &&
            (!rule.product_ids.length || rule.product_ids.includes(product.value)) &&
            (!rule.journey_ids.length || rule.journey_ids.includes(journey.value)),
        );
        status.textContent = `Domain pack v${pack.version} · ${approved.length} applicable approved rules. Catalogue focus is reference-only; missing business rules must be supplied by the owner.`;
      };
      product.addEventListener("change", update);
      journey.addEventListener("change", update);
      update();
    })
    .catch((error) => {
      product.disabled = true;
      journey.disabled = true;
      status.textContent = error.message;
    });
})();
