# UK Quotation Services ReqnRoll policy

Use the profile's BRD v1.0 baseline as the sole domain semantics source. Generate bindings only for
the supplied Quality Gate-approved automation Gherkin; the BRD validates meanings and expected
contracts but is not permission to invent additional scenarios, endpoints, payload fields, or
calculation formulas.

Support reusable bindings for every supplied BRD validation scenario, including canonical request
construction for `POST /api/v1/quotations`, configured invalid/missing/boundary/effective-date test
data, and assertions for all supplied business errors. Typed response assertions cover `status`,
exact `code`, safe `message`, optional `field`, `correlationId`, and absence of stack traces or
confidential calculation details.

Keep financial values as C# `decimal`; deserialize into typed quotation/error records. Represent
brand, product, customer type, maintenance option, quote date, expected code, and oracle/version
fields as typed parameters or transformations when reused. Do not hard-code 20% VAT, eligibility
limits, rates, APR, residuals, fees, maintenance prices, CAC, expected payments, service URLs, or
credentials. Approved golden/reference data belongs in injected fixtures or Examples-derived
scenario data.

The coverage map must preserve each scenario's `BR-QT-*` traceability in the artifact notes and
classify every unique validation step as reused, generated, or blocked. A missing implementation
detail is blocked/TODO, never guessed.
