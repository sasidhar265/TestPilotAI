# UK Quotation Services quality-gate policy

Reject output that conflicts with BRD v1.0, omits applicable `BR-QT-*` mappings, invents finance or
VAT/APR/CAC rules, infers regulation from product code, applies expired configuration, performs an
invalid calculation instead of returning a BRD error, leaks confidential details, or adds
out-of-scope credit/application/contract/payment behavior.

Reject unsupported catalogue drift: Conditional Sale, Lamborghini, targeted/non-targeted APR
solver modes, non-canonical brand casing, or lifecycle endpoints/behaviors not supplied by current
requirements. For full catalogue coverage require all eleven BRD brands, seven products, and three
maintenance codes, with documented risk-based consolidation rather than a blind Cartesian suite.

For calculation requests require applicable amount-of-credit/finance reconciliation and the
correct product shape:

- PCP includes mileage and GFV/optional final payment when required.
- HP normally avoids a large GFV unless configured otherwise.
- LP accounts for its balloon in instalments.
- PCH/BCH test rental, mileage, maintenance, excess mileage and VAT; BCH exposes net/tax/gross.
- PFL/BFL follow their separately approved definitions; BFL exposes net/tax/gross where required.

Reject exact instalment, rental, interest, APR, GFV/residual, VAT, maintenance, CAC or total values
without a named approved golden quotation, reference calculator, configured rule or pinned fixture.
Require decimal-safe comparison, approved rounding/tolerance, effective-date/version traceability,
and reconciliation appropriate to the product. Treat the stated current 20% VAT rate as configured,
not hard-coded. Treat representative APR separately from an individual quote APR.

Require exact BRD error codes and the `status`, `code`, safe `message`, optional `field`, and
`correlationId` shape. Reject assertions requiring timestamp/HTTP-status fields absent from the
BRD. Require authentication/authorization, safe observability and applicable average <1s/P95 <2s
performance coverage when in scope.

For complete BRD generation, reject both manual and automation suites if any Mandatory validation
inventory item or any of the nineteen BRD business error codes lacks a mapped case. A consolidated
Scenario Outline is acceptable only when every error row remains explicit and traceable. Manual
cases use structured actions with `gherkin: null`; automation cases require executable Gherkin and
typed synthetic data suitable for ReqnRoll bindings.

For automation Gherkin require Given/When/Then, no more than four executable step lines, and no
step text over 100 characters. Detailed values belong in Examples or structured test data.
