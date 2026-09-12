# UK Automotive Quotation Services project profile

The current request and its explicit business rules define the requested scope. Use the
version-controlled BRD v1.0 baseline in `knowledge/quotation-brd-baseline.md` as the default
domain requirements source for quotation behavior when the request does not provide it.
This profile and its specialist overlays apply only to relevant quotation behavior. Do not impose
quotation calculations, catalogue coverage or BR-QT requirements on supplied queue, enrichment,
documentation or other service requirements. Preserve supplied FR-* and BR-* identifiers;
preserve BR-QT-* identifiers where the request uses the quotation baseline. Current explicit
requirements take precedence over default domain examples. A direct contradiction within the
supplied requirements still needs clarification, not invented semantics. Ignore conflicting
stored examples, older quotation drafts, and unstated domain conventions.
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

## Input model — current user-approved contract

The user's supplied request in `app/templates/framework/QuotationRequest.Json` supersedes
older BRD request-shape examples. Its ONLY body sections and fields are:

- Outlet: `code`.
- Finance: `ProductId`.
- Vehicle: `CapCode`, `VehicleRegistrationNumber`, `VehicleRegstrationDate`, `VehicleMake`,
  `PriceTotal`, `YearOfManufacture`, `ExteriorColor`, `QualifyingOrMargin`.
- Parameters: `Deposit`, `Term`, `AnnualMileage`, `CustomerRate`, `PartExchange`, `Settlement`,
  `CalcTargetType`.

Preserve exact wire spelling/casing (including `VehicleRegstrationDate`). Use the provided
values as the default request, not inferred business-valid values. Build it through a typed
fluent QuotationRequestBuilder; override only known fields using supplied Examples/fixtures.
Money/rates use decimal arithmetic; the registration date remains a date-only string.
Customer type, eligibility, product catalogues, oracle expectations, maintenance and version
metadata belong in separate test context when supported; never add them to this request.
If a scenario requires an unavailable payload field or unsupported mapping, report the contract
gap instead of inventing a field. Endpoint path/method and credentials remain runtime configuration.
Do not infer a successful status or financial result from the sample payload.

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
