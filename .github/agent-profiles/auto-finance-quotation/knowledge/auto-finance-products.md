# Auto finance product knowledge

Version: 1.0
Status: reference_only — proposed analysis and test-design guidance; business approval pending.
Owner: unassigned; responsible business function identified below must review.
Reviewed: 2026-10-13
Scope: UK-oriented terminology; deployment market remains unspecified.
Authority: existing quotation BRD/profile for project scope; public sources for terminology only.
Do not turn this guidance into governing rules, contract fields or executable financial expectations.
Apply lifecycle material only when explicitly requested; quotation scope remains unchanged.

## Product distinctions and approval questions

| Product | Reference model | Information required from Product and Finance |
| --- | --- | --- |
| HP | Purchase-oriented instalment finance; ownership conditions belong to the agreement | Financed balance, payment timing, rate method, fees and ownership prerequisites |
| PCP | Regular instalments and an optional final ownership payment; distinguish GFV from current vehicle valuation | GFV source/version, return conditions, purchase fee, mileage and end-of-term options |
| LP | Finance with a balloon/final amount affecting the regular instalments | Whether the final amount is mandatory, refinancing assumptions, residual risk and ownership terms |
| PCH | Personal rental arrangement; distinguish rental from credit repayment | Initial rental profile, service inclusions, mileage, return condition and tax treatment |
| BCH | Business contract hire; preserve net, VAT and gross components where applicable | Customer eligibility, rental schedule, maintenance and component tax treatment |
| PFL | Project-defined personal finance lease | Approved legal/product definition, residual exposure, final rental and disposal arrangements |
| BFL | Project-defined business finance lease | Approved product definition, residual/final rental, disposal treatment and customer obligations |

## Shared concepts

Cash price is the vehicle price under the approved contract. Deposit, part exchange,
settlement of an existing agreement and contributions are distinct inputs: define their signs
and allocations before deriving credit. Negative equity needs an explicit financing policy.
A financed fee increases the balance only when approved; an upfront fee is a separate cashflow.
Residual value is an assumption or valuation; GFV and balloon have contract-specific meanings.
Nominal interest and APR are different measures; neither can be inferred from a field name.
An initial rental is not automatically a refundable deposit. Maintenance codes S/SM/SMT have
configured service contents; do not infer those contents from the abbreviations.

## Evidence and risks

Require a dated product specification, supported customer/brand matrix, approved cashflow
examples, pricing version and agreement terms. Review missing versus zero values, fee double
counting, deposit/contribution allocation, residual changes, final payment timing and mixed
product assumptions. Only known quotation payload fields may enter requests; missing product
inputs are contract gaps, not permission to extend the wire contract.

## Sources

- Repository quotation-services-product-catalog.md and quotation-brd-baseline.md (draft).
- MoneyHelper PCP terminology: https://www.moneyhelper.org.uk/en/everyday-money/buying-and-running-a-car/financing-buying-car-personal-contract-purchase-pcp
- MoneyHelper finance overview: https://www.moneyhelper.org.uk/en/everyday-money/buying-and-running-a-car/whats-the-best-way-to-finance-buying-a-car
