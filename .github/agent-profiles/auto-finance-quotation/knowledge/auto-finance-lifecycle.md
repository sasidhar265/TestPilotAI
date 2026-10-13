# Auto finance lifecycle knowledge

Version: 1.0
Status: reference_only — proposed analysis and test-design guidance; business approval pending.
Owner: unassigned; responsible business function identified below must review.
Reviewed: 2026-10-13
Scope: UK-oriented terminology; deployment market remains unspecified.
Authority: existing quotation BRD/profile for project scope; public sources for terminology only.
Do not turn this guidance into governing rules, contract fields or executable financial expectations.
Apply lifecycle material only when explicitly requested; quotation scope remains unchanged.

## Journey analysis inventory

These are proposed review dimensions, not implemented workflows or approved state names.
Owners must supply actual transitions, integrations, permissions and acceptance criteria.

| Journey | Inputs and decisions to clarify | Evidence and exception cases to request | Review function |
| --- | --- | --- | --- |
| Quotation | Product, vehicle, deposit, term, mileage, rates, contributions, fees, residual and pricing date | Approved request/response, effective configuration, independent quote examples, unavailable rate/residual and expired campaign cases | Product / Finance |
| Application and identity | Applicant and vehicle linkage, consent, identity evidence, duplicate application handling | Identity outcomes, consent record, retry/timeout behavior, missing or inconsistent information; no assumed KYC/AML outcomes | Operations / Compliance |
| Underwriting | Credit risk, affordability, policy inputs and decision authority | Approved decision matrix, refer/decline/accept outcomes where defined, stale/missing bureau data, manual overrides and audit | Credit Risk |
| Agreement and activation | Accepted quotation version, agreement terms, signature evidence and activation prerequisites | Version mismatch, expired offer, missing acceptance, duplicate activation and failure recovery | Legal / Operations |
| Payments and servicing | Due schedule, actual receipt, allocation, refunds and account changes | Ledger reconciliation, partial/over/duplicate payment, reversal, failed collection and concurrent updates | Servicing / Finance |
| Arrears | Missed obligations, account status, customer circumstances and permitted support | Approved arrears definitions, communications, arrangements, cure criteria, recovery authorisation and audit | Collections / Compliance |
| Settlement and closure | Settlement date, balance, approved rebates/fees and closure prerequisites | Independent settlement examples, validity period, partial settlement, pending collections, overpayment and ledger closure | Finance / Servicing |

## State and integration reasoning

Record each approved transition as previous state, trigger, prerequisites, next state,
financial effects, customer communication and evidence. Separate business rejection from
technical failure. Clarify correlation keys, retry and duplicate-event semantics, reconciliation
ownership and recovery after partially completed work. Do not assume idempotency or an endpoint
exists merely because it would be useful.

## Regulatory reference boundaries

Credit risk and affordability require separate analysis; the lender must supply the approved
assessment method and applicable policy. Arrears support and recovery require jurisdiction and
agreement-specific compliance review. Public guidance cannot establish this project's thresholds,
notice periods, repossession rights, settlement formula or customer eligibility.

## Sources

- FCA CONC 5 responsible lending: https://handbook.fca.org.uk/handbook/conc5
- FCA CONC 7 arrears, default and recovery: https://handbook.fca.org.uk/handbook/conc7
- Repository domain journey catalogue; journeys beyond quotation are outside the draft quotation BRD.
