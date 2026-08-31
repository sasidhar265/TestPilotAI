# UK Quotation Services automation policy

Generate API-focused deterministic tests for `POST /api/v1/quotations` and approved downstream
contracts. Do not invent retrieval, recalculation, cancellation, expiry, idempotency, target-APR
solver modes, or other lifecycle behavior absent from BRD v1.0.

Prioritize this risk-based matrix:

1. Request/authentication plus every item in the profile's Mandatory validation inventory, with
   exact BRD error codes. Do not summarize or sample this inventory when complete BRD coverage is
   requested: every validation and all nineteen error codes need at least one mapped negative case.
2. Amount-of-credit reconciliation using applicable cash price, deposit and itemized contributions;
   cover fees, part exchange and negative equity only when an approved rule defines treatment.
3. Product-specific oracles: PCP GFV, HP amortization, LP balloon, PCH/BCH rentals, PFL/BFL rules,
   and product-appropriate final payments, mileage, maintenance and fees.
4. VAT configuration by component/customer/product/effective date, including net/tax/gross output
   for business products and configured inc-/ex-VAT output where required.
5. APR, total charge and total payable against approved UK golden/reference calculations; keep
   representative APR separate from individual quote APR.
6. Residual/GFV, maintenance, contributions, campaigns, fees and pricing at effective-date and
   expiry boundaries; never use expired configuration.
7. Decimal precision, approved rounding points/tolerance, schedule reconciliation, and identical
   outputs for identical inputs and versions.
8. Quote ID, pricing/calculation versions, correlation/audit evidence, safe errors/logs, dependency
   failures, horizontal-load behavior, average <1s and P95 <2s targets where testable.

Use decimal strings in JSON and C# `decimal`. Every exact expected instalment, rental, APR, GFV,
VAT or total must name an approved golden quotation, reference calculator, or pinned engine fixture.
Otherwise assert schemas, version use, eligibility outcomes, arithmetic identities supported by the
BRD, or owner-approved tolerances. Never make 20% VAT a permanent engine assumption.

For catalogue suites, use canonical columns such as `brand`, `productType`, `customerType`,
`maintenanceOption`, `quoteDate`, `oracleVersion`, `expectedStatus`, and `expectedCode`. Use
risk-based pairwise coverage plus mandatory/prohibited combinations and boundaries. Full catalogue
means all eleven BRD brands—not Lamborghini—all seven products, and `S`, `SM`, `SMT` at least once.

Keep each Scenario/Outline at exactly one Given, one When, and one Then where possible, never more
than four executable step lines, and no step text over 100 characters. Put detailed combinations
and calculation inputs in Examples and structured `test_data`.

For each automated validation scenario, make the Gherkin directly implementable: use stable domain
phrasing for the configured invalid condition, submit one quotation request, and assert the exact
response code and safe error contract. Ensure every placeholder has typed, synthetic test data so
the ReqnRoll generator can bind it without inventing API behavior.
