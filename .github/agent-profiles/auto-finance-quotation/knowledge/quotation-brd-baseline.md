# UK Automotive Quotation Services API BRD baseline v1.0

Source: `Business Requirements.pdf`, 31 pages. Version 1.0; example quote date 2026-08-31;
status **Draft for Business, Product, Architecture and Compliance Review**. Preserve source IDs
`BR-QT-001` through `BR-QT-028`. This supersedes profile material mentioning Conditional Sale,
quote lifecycle endpoints, Lamborghini, or targeted APR modes.

## Purpose, boundaries, and governing principle

The API is the authoritative centralized calculator for supported UK automotive finance and
leasing quotations across dealer, web, mobile, digital retail, contact centre, partner, fleet,
internal finance, comparison, and finance-application journeys. It authenticates consumers,
validates requests, resolves effective configuration, calculates, and returns an auditable GBP
quotation.

Keep product calculation, pricing configuration, tax treatment, regulatory classification, and
customer presentation separate. Product availability, eligibility, rates, VAT, residual/GFV,
maintenance, fees, campaigns, contributions, CAC, and regulatory treatment are configuration-led
and effective-dated where applicable. Never infer regulatory treatment from a product code.

Out of scope unless separately required: credit searches, affordability, scoring/decisioning,
KYC, AML, application submission, contract generation, e-signature, Direct Debit, vehicle
ordering, payment collection, complaints/redress calculation, and account servicing.

## Catalogue and classifications

- Products: `PCP`, `HP`, `LP`, `PCH`, `BCH`, `PFL`, `BFL`.
- Brands: `AUDI`, `SKODA`, `SEAT`, `CUPRA`, `VWPC`, `VWCV`, `TATA`, `MAHINDRA`,
  `TOYOTA`, `PORSCHE`, `BENTLEY`.
- Maintenance: `S`, `SM`, `SMT`; included services are configured, not hard-coded.
- Customer types include private individual, sole trader, partnership, limited company, public
  sector organisation, fleet customer, and other business customer.
- Example regulatory classes: `REGULATED`, `UNREGULATED`, `EXEMPT`, `BUSINESS`,
  `NOT_APPLICABLE`; definitions require Legal and Compliance approval.

Use `quotation-services-product-catalog.md` for canonical values and product distinctions.

## Request and flow

The core request supports `brand`, `productType`, `customerType`, `vehicleId`,
`vehicleCashPrice`, `deposit`, `termMonths`, `annualMileage`, `maintenanceOption`, and
`quoteDate`, plus product-specific inputs. Vehicle data may include manufacturer, model/year/
derivative/type, fuel, transmission, condition, registration/current mileage, prices and VAT,
options/accessories, delivery, registration, and other charges. Financial data may include
deposit percentage, part exchange, negative equity, contributions, finance amount, rate/APR,
mileage, residual/GFV/balloon, initial rental, payment profile, maintenance, and fees.

The flow is authentication; structure and business validation; product/pricing/rate/residual/
maintenance/campaign resolution; contribution application; finance/rental calculation; tax and
regulatory processing; Quote ID; response. The endpoint example is `POST /api/v1/quotations`.
The BRD does not define retrieval, recalculation, cancellation, expiry, or idempotency behavior.

## Product-specific calculation shape

- PCP: amount of credit, term/rate/APR, regular instalments, GFV/optional final payment,
  applicable option-to-purchase fee, total charge/payable, mileage and excess-mileage information.
- HP: amount financed, term/rate/APR, instalment, fees/optional purchase fee, total charge/payable;
  normally amortizes without a large GFV, subject to configured rules.
- LP: finance amount, term/rate, instalment, balloon/final payment, fees, interest, total payable;
  the balloon affects regular instalments.
- PCH: initial/monthly rental, term, mileage, maintenance rental, VAT, excess-mileage rate, fees;
  return inc-VAT and, where required, underlying ex-VAT values.
- BCH: initial/regular rental, term, mileage, residual, maintenance, excess mileage, VAT; expose
  rental net, VAT, and gross.
- PFL: initial/monthly rental/payment, term, mileage, residual assumptions, maintenance, VAT,
  fees and applicable final rental, using the approved PFL definition.
- BFL: initial/regular rental, finance amount, term, residual/balloon, maintenance, VAT, fees and
  applicable final rental; expose net, VAT and gross where required.

## Cross-cutting financial and regulatory rules

- VAT rate and treatment are configured by product, vehicle, customer type, payment component,
  maintenance component, fee, and effective date. The noted current 20% rate is not hard-coded.
- Applicable APR uses approved UK methodology and total-cost-of-credit elements. Return rate, APR,
  charge for credit, amount of credit, and total payable. Representative APR is separate from an
  individual quotation APR. Never invent either formula.
- Maintenance price may depend on vehicle characteristics, term/mileage, package and date; return
  ex-VAT, VAT and inc-VAT amounts where applicable.
- Residual/GFV may depend on brand/model/derivative/fuel, vehicle age, term, mileage and quote date
  and comes from approved configuration or a downstream service.
- Contributions include manufacturer deposit, dealer, finance deposit allowance, campaign,
  vehicle/customer/fleet discounts, and other incentives. Preserve type, amount, funding source,
  campaign ID and effective date. Never apply expired campaigns.
- Commission is separate from interest logic, traceable, and must not implement prohibited
  discretionary commission arrangements.
- CAC remains a configurable placeholder until Product/Finance confirms its definition, formula,
  product applicability and visibility. Do not invent CAC behavior.
- Use decimal arithmetic and enough internal precision. GBP display amounts normally have two
  decimals. Round only at approved points using approved rules.
- Reconcile cash price minus deposit/contributions to amount of credit and relevant deposit,
  instalments, final payment and fees to total payable within approved tolerance. Exact payments,
  rentals, APR and totals require approved golden examples or an approved independent oracle.

## Response, validation, and errors

An applicable success response includes Quote ID, GBP currency, brand/product/customer type,
regulatory class, price/deposit/itemized contributions, amount of credit, term/mileage, rate/APR,
monthly payment or rental, maintenance, final/balloon payment, total charge/payable, pricing
version and calculation version. Every persisted quotation has a unique, auditable Quote ID.

Validate active brand/product, configured brand-product and customer-product eligibility, vehicle
and price limits, deposit, approved term, mileage, permitted maintenance, required residual/rate,
and campaign validity on `quoteDate`. Standard errors are `INVALID_BRAND`, `INVALID_PRODUCT`,
`INVALID_CUSTOMER_TYPE`, `INVALID_VEHICLE`, `INVALID_VEHICLE_PRICE`, `INVALID_DEPOSIT`,
`INVALID_TERM`, `INVALID_MILEAGE`, `INVALID_MAINTENANCE_OPTION`,
`PRODUCT_NOT_AVAILABLE_FOR_BRAND`, `PRODUCT_NOT_AVAILABLE_FOR_CUSTOMER`,
`CAMPAIGN_NOT_APPLICABLE`, `CAMPAIGN_EXPIRED`, `INTEREST_RATE_NOT_AVAILABLE`,
`RESIDUAL_VALUE_NOT_AVAILABLE`, `MAINTENANCE_RATE_NOT_AVAILABLE`,
`PRICING_CONFIGURATION_NOT_AVAILABLE`, `INVALID_CALCULATION_INPUT`, and `CALCULATION_FAILED`.

The error body has `status`, `code`, safe `message`, optional `field`, and `correlationId`.
Never expose stack traces or confidential calculation details. Persisted audit trace covers quote
identity/time, brand/product/customer, request/pricing, rate/APR, contributions, residual/GFV,
maintenance, VAT, CAC/commission where applicable, versions, response, and correlation ID.

## Core requirements

| ID | Required capability |
|---|---|
| `BR-QT-001` | Generate supported UK automotive quotations |
| `BR-QT-002` | Support all seven products |
| `BR-QT-003` | Support all eleven named brands |
| `BR-QT-004` | Support S, SM and SMT maintenance |
| `BR-QT-005` | Validate brand/product eligibility |
| `BR-QT-006` | Validate customer/product eligibility |
| `BR-QT-007` | Calculate amount of credit where applicable |
| `BR-QT-008` | Calculate monthly finance instalments |
| `BR-QT-009` | Calculate monthly leasing rentals |
| `BR-QT-010` | Calculate APR where applicable |
| `BR-QT-011` | Calculate total charge for credit where applicable |
| `BR-QT-012` | Calculate total amount payable |
| `BR-QT-013` | Calculate GFV/final payments where applicable |
| `BR-QT-014` | Incorporate residual values |
| `BR-QT-015` | Calculate VAT where applicable |
| `BR-QT-016` | Return ex-VAT and inc-VAT amounts where required |
| `BR-QT-017` | Calculate maintenance payments |
| `BR-QT-018` | Support campaign contributions |
| `BR-QT-019` | Support manufacturer/dealer contributions |
| `BR-QT-020` | Support configurable fees |
| `BR-QT-021` | Support configurable CAC, subject to definition approval |
| `BR-QT-022` | Provide calculation traceability |
| `BR-QT-023` | Support effective-dated pricing |
| `BR-QT-024` | Apply approved rounding rules |
| `BR-QT-025` | Produce consistent output for identical input/configuration |
| `BR-QT-026` | Return validation errors instead of invalid calculations |
| `BR-QT-027` | Retain pricing/calculation versions for persisted quotes |
| `BR-QT-028` | Support downstream regulated disclosures |

## Non-functional and release gates

Target average response is under one second and P95 under two seconds, excluding agreed exceptional
downstream latency. Availability is 99.9% or agreed SLA, with horizontal scaling. Require TLS,
authentication, application authorization, least privilege, financial-data restrictions and UK
GDPR protections. Monitor volume, outcomes/failures, latency/timeouts and brand/product failures
without unnecessary sensitive data. Breaking contracts require an API version; pricing changes
normally use effective-dated configuration.

Release needs approved scenarios for all products/brands/maintenance, UK APR and VAT reference
agreement, contribution/residual reconciliation, expired configuration rejection, determinism,
version traceability, and regulatory output. Compliance approves classification/APR/commission;
Finance formulas; Tax VAT; Product rules; Pricing rates/campaigns. Approved golden quotations are
required for automated financial regression values.
