/* Reference-only exploration: never changes the approved source or request payload. */
(() => {
  const products = {
    PCP: [
      "PURCHASE FINANCE",
      "Personal Contract Purchase",
      "Follow the quotation from regular instalments to guaranteed future value and optional final payment.",
      ["Deposit, term and mileage", "GFV and optional final payment", "Total charge and payable"],
    ],
    HP: [
      "PURCHASE FINANCE",
      "Hire Purchase",
      "Trace the amount financed through instalments, applicable fees and the total payable.",
      [
        "Amount financed and deposit",
        "Instalments and applicable fees",
        "Financial reconciliation",
      ],
    ],
    LP: [
      "PURCHASE FINANCE",
      "Lease Purchase",
      "Review how the approved balloon payment contributes to the quotation and regular instalments.",
      ["Balloon or final payment", "Term and approved rate", "Interest and total payable"],
    ],
    PCH: [
      "PERSONAL LEASING",
      "Personal Contract Hire",
      "Explore initial and regular rentals with mileage, maintenance and the approved VAT treatment.",
      ["Initial and regular rentals", "Mileage and maintenance", "Applicable VAT and fees"],
    ],
    BCH: [
      "BUSINESS LEASING",
      "Business Contract Hire",
      "Reconcile rental net, VAT and gross values against approved business eligibility and pricing.",
      ["Configured business eligibility", "Rental net, VAT and gross", "Mileage and maintenance"],
    ],
    PFL: [
      "PERSONAL LEASING",
      "Personal Finance Lease",
      "Build coverage around the approved PFL definition and its rental and maintenance structure.",
      ["Approved rental structure", "Residual assumptions", "Applicable final rental"],
    ],
    BFL: [
      "BUSINESS LEASING",
      "Business Finance Lease",
      "Trace the finance amount, rental profile and residual or balloon through approved business lease rules.",
      ["Finance amount and rentals", "Residual or balloon", "Applicable net, VAT and gross"],
    ],
  };
  const byId = (id) => document.getElementById(id);
  document.querySelectorAll("[data-finance-product]").forEach((button) => {
    button.addEventListener("click", () => {
      const [category, name, description, focus] = products[button.dataset.financeProduct];
      document.querySelectorAll("[data-finance-product]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      byId("finance-product-category").textContent = category;
      byId("finance-product-name").textContent = name;
      byId("finance-product-description").textContent = description;
      byId("finance-product-focus").replaceChildren(
        ...focus.map((label) => {
          const item = document.createElement("li");
          item.textContent = label;
          return item;
        }),
      );
    });
  });
  byId("finance-start").addEventListener("click", () => {
    byId("description").focus({ preventScroll: true });
    byId("test-studio").scrollIntoView({ block: "start" });
  });
  byId("finance-explore").addEventListener("click", () => {
    document
      .querySelector('[data-finance-product][aria-pressed="true"]')
      .focus({ preventScroll: true });
    document.querySelector(".finance-explorer").scrollIntoView({ block: "center" });
  });
})();
