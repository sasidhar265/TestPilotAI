# UK Automotive Quotation Services project profile

Use the version-controlled BRD v1.0 baseline in `knowledge/quotation-brd-baseline.md` as the sole
domain requirements source for manual cases, automation cases, and step definitions. The current
request may select scope or output format but must not add business behavior. Ignore conflicting
stored examples, older quotation drafts, and unstated domain conventions. Preserve `BR-QT-*` IDs.
Do not invent formulas, thresholds,
eligibility matrices, maintenance contents, VAT treatment, regulatory classifications, disclosure
wording, rounding/tolerance, or CAC rules that await owner approval.

Apply the canonical catalogue in `knowledge/quotation-services-product-catalog.md`. The project
supports seven products, eleven brands, and three maintenance codes. Consolidate shared behavior;
do not multiply cases merely to enumerate catalogue values. Treat regulatory classification as
approved configuration, never as an inference from product code.

Prioritize product-specific calculation correctness, eligibility, price/deposit/term/mileage
boundaries, effective-dated rates/campaigns/residuals/maintenance/VAT, contribution and fee
application, precision/reconciliation, deterministic versioned results, safe validation errors,
authentication/authorization, auditability, regulatory output, resilience, and performance.
Use GBP and decimal money. Keep out-of-scope credit, KYC/AML, application, contracting, ordering,
payment and servicing behavior out of generated requirements.

## Input model

Use only current requirement or BRD fields, grouped where applicable:

- Identity: authorized application/channel, correlation ID, quote date/time, market and customer
  type. Do not add idempotency unless newer requirements do.
- Vehicle: ID, manufacturer/brand, model/year/derivative/type, fuel/transmission, new/used,
  registration/current mileage, base/VAT/retail/on-road/cash prices, options and charges.
- Product: product code, term, annual/total mileage, initial rental/payment profile, rate/APR,
  residual/GFV/balloon/final payment, and effective product/rate/calculation versions.
- Money: deposit, part exchange/negative equity, itemized contributions/discounts with source,
  fees, maintenance net/VAT/gross, payment/rental net/VAT/gross, and CAC/commission only where an
  approved rule applies.
- Oracle: amount of credit/finance, instalment or rental, payment count/final payment, total charge,
  total payable, VAT, APR, rounding/tolerance source and approved golden/reference version.

Never require every field for every product. Missing mandatory data becomes negative coverage.
Missing formulas or approved oracle values become assumptions, contract checks or reconciliation
invariants—not fabricated exact results.

## Output and error expectations

Assert applicable response fields: Quote ID, currency, canonical brand/product/customer type,
regulatory class, itemized prices/deposits/contributions/fees, amount of credit, rate/APR, term and
mileage, regular payment/rental, maintenance, final/balloon/GFV, VAT net/tax/gross, total charge and
payable, pricing/calculation versions, and correlation/audit evidence.

Use the BRD error schema: `status`, `code`, safe `message`, optional `field`, and `correlationId`.
Use exact BRD business error codes. Do not require timestamp, HTTP-status fields, lifecycle links,
or endpoints absent from the current BRD.

## Mandatory validation inventory

Both manual and automation suites must cover every applicable validation below, with positive,
negative, missing-value, configured-boundary, and effective-date cases where the BRD supports them:

- active supported brand, product, and configured brand/product combination;
- supported customer type and configured customer/product eligibility;
- valid vehicle and configured vehicle-price limits;
- deposit minimum/maximum and invalid deposit;
- approved term and configured mileage limits;
- permitted maintenance option and available maintenance rate;
- required interest rate and residual value availability;
- applicable and unexpired campaign on the quotation date;
- available effective-dated pricing configuration and valid calculation inputs;
- authentication, application authorization, safe errors, and calculation failure handling.

Across the suite, map all nineteen BRD business errors exactly and do not replace them with older
aliases. Each error case asserts `status`, `code`, safe `message`, relevant `field` when supplied,
and `correlationId`, plus absence of stack traces or confidential calculation details.
