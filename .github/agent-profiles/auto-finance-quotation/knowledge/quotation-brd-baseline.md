# Quotation Service BRD baseline v1.0

Project: Auto Finance Platform. Component: Quotation Service APIs. Status: Draft.

## Purpose and scope

Provide centralized real-time indicative or formal vehicle-finance quotations consistently across
web, mobile, dealer, partner, and downstream finance channels. Inputs include vehicle price,
deposit, product, term, interest, mileage, final payment, fees, contributions, promotions,
eligibility, and taxes. Outputs include monthly payment, deposit, amount financed, interest, APR,
total payable, final payment, duration, identifiers, status, creation time, and expiry.

Supported products include Hire Purchase (HP), Personal Contract Purchase (PCP), and Conditional
Sale. In scope: create, recalculate, retrieve, cancel/status, validate, calculate, store, audit,
authenticate, authorize, integrate with product/rate/promotion/residual/dealer/vehicle services,
and return standardized errors. Credit checks, KYC, AML, affordability unless explicitly needed
for quote eligibility, application submission, ordering, payments, account creation, signing,
delivery, Direct Debit, and collections are out of scope.

## Authoritative business rules

- BR-001 Create quotation: an authorized consumer can request a quote; generate a unique Quote ID
  such as `QT-20260827-123456`.
- BR-002 Vehicle information: support vehicle ID, optional VIN/registration, manufacturer, model,
  variant, year, condition, new/used indicator, and cash price.
- BR-003 Vehicle price: purchase price is mandatory and greater than zero.
- BR-004 Customer deposit: support deposit and enforce configured product minimum/maximum rules.
- BR-005 Part exchange: include it in total customer contribution where applicable.
- BR-006 Dealer contribution: support it and reduce amount financed according to product rules.
- BR-007 Manufacturer contribution: eligibility can depend on vehicle, product, term, campaign,
  and quote date.
- Amount financed normally equals vehicle price plus financed fees minus customer deposit, part
  exchange, dealer contribution, and manufacturer contribution. Product-specific rules prevail.
- BR-008 Interest rate: resolve from configurable rules/source using product, vehicle/age,
  manufacturer, finance amount, term, campaign, dealer, and customer category where applicable.
- BR-009 APR: calculate consistently using applicable interest, fees, charges, schedule, product,
  and regulatory rules. Exact approved formulas are not supplied by this draft.
- BR-010 Finance term: terms are configurable and product-dependent; reject unsupported terms.
  Examples: HP 12–60 months and PCP 24–48 months.
- BR-011 Annual mileage: PCP requires supported mileage and mileage may affect GFV.
- BR-012 Final payment: PCP-like products may return optional final/balloon payment and GFV based
  on vehicle, age, term, mileage, and expected future value.
- BR-013 Monthly payment: calculate using amount financed, rate, term, fees, final payment, and
  frequency; return payment count and final payment.
- BR-014 Fees: support arrangement, option-to-purchase, documentation, and administration fees;
  identify upfront, financed, or final-payment treatment.
- BR-015 Promotions: enforce ID, dates, eligible vehicle/product, rate, contribution, and
  conditions. Never apply expired promotions.
- BR-016 Quote expiry: return creation and expiry timestamps; expired quotes may become `EXPIRED`
  and may require a new quote if rates or products changed.
- Quote statuses: `DRAFT`, `GENERATED`, `SAVED`, `ACCEPTED`, `EXPIRED`, `CANCELLED`, `SUPERSEDED`.
- BR-017 Mandatory validation: vehicle ID, price, product, deposit, and term are mandatory.
- BR-018 Deposit: non-negative, not above vehicle price, within configured product limits.
- BR-019 Term: must be supported by the selected product; PCP 60 months is an invalid example.
- BR-020 Mileage: required for mileage-based products and within configurable min/max.
- BR-021 Price: greater than zero, supported currency, within product limits.
- BR-022 Product eligibility: validate vehicle, dealer, market, amount, term, and campaign.
- BR-023 Authentication: require an authenticated consumer using organizational OAuth 2.0, JWT,
  or API Gateway standards as finalized by architecture.
- BR-024 Authorization: enforce channel, dealer, partner, application, and role permissions.
- BR-025 Encryption: HTTPS/TLS and enterprise-standard encryption for sensitive information.

## API contracts and errors

- `POST /api/v1/quotes`: create a quote, normally returning 201.
- `GET /api/v1/quotes/{quoteId}`: retrieve an existing quote.
- `POST /api/v1/quotes/{quoteId}/recalculate`: recalculate changed deposit, term, mileage, or
  product and either version the quote or link original/recalculated quotes per final design.
- Cancel using `DELETE /api/v1/quotes/{quoteId}` or `PATCH /api/v1/quotes/{quoteId}/status`, pending
  final API design.
- Standard error payload contains timestamp, HTTP status, errorCode, message, and correlationId.
- Status expectations: 200 success, 201 created, 400 invalid request, 401 authentication, 403
  authorization, 404 missing quote, 409 conflict, 422 business validation, 429 rate limit, 500
  internal error, 502 downstream unavailable, 503 temporarily unavailable.
- Business errors: `INVALID_VEHICLE_PRICE`, `INVALID_DEPOSIT`, `INVALID_FINANCE_TERM`,
  `INVALID_MILEAGE`, `PRODUCT_NOT_AVAILABLE`, `RATE_NOT_AVAILABLE`, `PROMOTION_EXPIRED`,
  `PROMOTION_NOT_ELIGIBLE`, `QUOTE_NOT_FOUND`, `QUOTE_EXPIRED`, `VEHICLE_NOT_ELIGIBLE`, and
  `CALCULATION_ERROR`.

## Calculation, data, audit, and lifecycle rules

The supplied worked PCP example uses vehicle price GBP 30,000, deposit 3,000, manufacturer
contribution 1,000, 48 months, annual mileage 10,000, rate 5.49%, amount financed 26,000, 47
monthly payments of 425.50, final payment 12,000, APR 5.9%, and total payable 35,998.50. Treat it
as a reference example, not a complete formula specification. Official rounding belongs to the
calculation engine; example 425.496 rounds to 425.50. Store a calculation version with every quote
so historic results are reproducible. Initial currency is GBP; architecture must allow expansion.

Audit data includes Quote ID, timestamp, requesting application, dealer/user/system ID, product,
status, calculation version, rate, promotion, and correlation ID. Operational monitoring includes
volume, success/failure, validation and downstream failures, latency, rate/product failures, and
calculation errors. Never expose sensitive customer or financial information in logs.

## Non-functional requirements

- NFR-001 Performance: normally respond within two seconds under expected production load,
  excluding exceptional downstream delays; final target requires solution-design approval.
- NFR-002 Availability: example target 99.9% monthly, subject to agreement.
- NFR-003 Scalability: horizontal scaling for campaigns, launches, and dealer peaks.
- NFR-004 Reliability: identical inputs produce consistent calculations while underlying rates,
  products, promotions, and versions are unchanged.
- NFR-005 Idempotency: where appropriate, `Idempotency-Key` prevents duplicate quotes on retries.
- NFR-006 Traceability: accept or generate `X-Correlation-ID` across downstream calls.
- Concurrent requests must remain isolated; one customer's quote cannot affect another's.
- Resilience coverage includes unavailable/time-out Vehicle, Product, Rate, Promotion, Residual
  Value, Dealer, database, gateway, IAM, monitoring, and logging dependencies.

## Regulatory and risk baseline

Customer disclosures may require representative APR, rate, credit amount, total payable, payment
count/amount, final payment, fees, cash price, and deposit. Legal and Compliance must approve final
wording and formulas. Highest risks are incorrect calculations/rates, expired promotions,
downstream unavailability, duplicate quotes, changing calculation rules, slow responses, and
unauthorized access.

## Business acceptance baseline

Tests must demonstrate: valid quote generation; unique IDs; correct use of price, deposits, dealer
and manufacturer contributions, interest, APR, monthly instalments, and PCP final payment;
rejection of unsupported products, terms, mileage, and expired promotions; retrieval,
recalculation, and expiry; unauthorized-request rejection; standardized errors; correlation-ID
traceability; and agreement with Finance Product Team-approved reference calculations.

## Assumptions requiring explicit treatment

Vehicle, product, rate, promotion, residual, and dealer data come from approved upstream sources.
Promotion dates are configurable. The quotation service does not perform a full credit assessment.
Final finance calculations, APR/regulatory formulas, disclosure wording, deposit/mileage/product
limits, cancellation method, quote versioning strategy, availability target, and retry policy need
approval from their named business, architecture, finance, legal, compliance, or operations owner.
