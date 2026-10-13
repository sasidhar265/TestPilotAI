# Auto finance calculations, data and evidence

Version: 1.0
Status: reference_only — proposed analysis and test-design guidance; business approval pending.
Owner: unassigned; responsible business function identified below must review.
Reviewed: 2026-10-13
Scope: UK-oriented terminology; deployment market remains unspecified.
Authority: existing quotation BRD/profile for project scope; public sources for terminology only.
Do not turn this guidance into governing rules, contract fields or executable financial expectations.
Apply lifecycle material only when explicitly requested; quotation scope remains unchanged.

## Calculation specification required for each product

Finance must supply the rate definition and units, payment frequency/timing, day-count and
compounding convention, treatment of contributions and equity, financed/upfront fees, residual
and final payments, tax allocation, rounding stages and reconciliation tolerance. Record the
applicable product, currency, effective dates and calculation version. No generic annuity can
serve as the oracle for all seven products.

The existing principal, annuity and VAT tools validate declared arithmetic conventions only.
They do not establish statutory APR, product pricing, lease rentals, flat-rate finance, early
settlement or rebate methods. APR requires an independently approved method and cashflow inputs.
VAT requires approved applicability and supplied rates; do not encode a universal tax rate.

## Proposed golden-example record

For an independently reviewed example retain: example ID/version; product/journey; policy and
pricing versions; effective date; synthetic input fixture and contract version; expected amounts
and full payment schedule; calculation method and independent oracle provenance; rounding and
tolerance; approver; approval date; and source document/version. These are evidence metadata,
not fields to add to the quotation request. Store no credentials or customer personal data.

Request examples for zero interest where supported, nearest permitted term/deposit/mileage
boundaries, final-payment rounding, financed versus upfront fees, multiple contributions,
negative equity where allowed, effective-date changes and tax component reconciliation.
Expected monetary values must come from the approved independent oracle, not the generated test
or the system under test. Mathematical tool fixtures are synthetic calculator examples only.

## Data ownership and integration contracts

Identify owners of product eligibility, vehicle data, pricing, rates, residual/GFV, maintenance,
campaigns, commission and tax configuration. For each source record version/effective date,
fallback permissions, missing-data behavior and audit identifiers. Stale data must not silently
be treated as current. Preserve existing request spelling/casing; unsupported inputs stay in
separate test context or become explicit contract questions.

## Traceability

Approved source/version → BR ID/version → explicitly mapped requirement/version → pinned suite
baseline → test acceptance_criteria_covered → execution → defect/retest evidence. The domain TOML
supports explicit mappings; do not infer them from product names. A traceability edge alone does
not prove execution or approval. Record the configuration tested and keep approved versions stable.

## Sources

- Repository docs/auto-finance-domain.md for exact calculator conventions and limitations.
- Repository quotation-risk-and-evidence.md for quotation risk and oracle requirements.
