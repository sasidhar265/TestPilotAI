# Auto Finance quotation risk and evidence playbook

Status: engineering test-design guidance, not additional approved business requirements.
Reviewed: 2026-09-27. Apply only within the requested quotation scope. Existing approved
payload, supplied requirements and product definitions take precedence. These risk prompts
must not introduce new BR-QT IDs, endpoints, mandatory fields, rules or numeric thresholds.
An unavailable rule is a requirements gap; an unavailable fixture is a configuration gap.
Neither is permission to invent a passing expected result.

## Product reasoning

Distinguish a PCP optional final ownership payment from regular instalments; exercise its
presence and treatment using the approved product definition. A hire-purchase repayment
schedule and a contract-hire rental schedule are different calculation shapes. Do not use
one shared repayment formula for PCP, HP, LP, PCH, BCH, PFL and BFL. PFL/BFL meanings remain
project-defined. Treat final payments, purchase fees and rental profiles separately in
fixtures and assertions. Do not expand quotation tests into exercising contract termination,
vehicle return, collections or ownership transfer unless those journeys are requested.

Background: MoneyHelper explains PCP's optional final payment and distinguishes purchase
from leasing. This is terminology grounding, not a calculator specification:
https://www.moneyhelper.org.uk/en/everyday-money/buying-and-running-a-car/financing-buying-car-personal-contract-purchase-pcp

## Select applicable risks, then obtain approved examples

| Risk | Test-design prompts | Required oracle/configuration |
| --- | --- | --- |
| Part exchange and settlement | Positive, zero and negative equity; deposit and contribution counted once; no silently discarded settlement | Approved sign convention, permitted financing treatment and reconciled quote |
| Price and deposit | Configured min/max and nearest permitted values on either side; absent versus zero versus null; deposit exceeding permitted amount | Product limits, numeric scale and rejection code |
| Payment schedule | Initial versus regular versus final payments; payment count versus term; final rounding adjustment; zero rate if supported | Dated cash-flow schedule, timing convention, component inclusion and rounding rule |
| Fees and contributions | Financed versus upfront fee; manufacturer/dealer contribution eligibility and stacking; fee counted once | Approved source and allocation rules, campaign version |
| Rate and APR | CustomerRate meaning and units; nominal rate versus APR; promotion display versus individual quote | Approved rate definition and independent APR/reference output |
| Vehicle and residual | Registration date/year consistency if required; unsupported CapCode; mileage/term/residual combinations | Approved vehicle mapping, date rules, residual table and version |
| Mileage and maintenance | Allowed mileage edges; supported maintenance code combinations; unavailable effective rate | Approved limits, units and component prices; never infer S/SM/SMT contents |
| Tax | QualifyingOrMargin treatment; taxable/exempt components; per-line versus total rounding | Approved tax treatment by component/date, expected net/tax/gross |
| Effective configuration | Immediately before/at/after activation and expiry; overlapping/missing versions; in-flight configuration changes | Approved timezone, boundary inclusivity and observable resolved versions |
| Access and isolation | Outlet entitlement and cross-outlet access; confidential pricing omitted from errors/logs | Approved credentials, outlet mapping and permitted evidence queries |
| Resilience | Rate/residual dependency unavailable; timeout; repeated request under pinned configuration | Approved errors, retry policy and deterministic field list |

Boundary increments must come from configured precision (money, percentage, months, miles,
dates); do not assume all inputs have a 0.01 increment. Never assume a lower instalment when
increasing a deposit or changing a term unless the approved rule fixes all other inputs,
fees, eligibility and campaign selection. Metamorphic checks supplement independent oracles.
Repeated financial results may be deterministic while quote IDs and correlation IDs change;
compare only approved stable fields. Repetition alone does not prove idempotency.

FCA CONC 3.5 concerns credit financial promotions and representative examples. Use it as a
review pointer when promotion output is explicitly in scope, not as proof every quotation
is a financial promotion or as an individual APR formula. Compliance must approve applicability:
https://handbook.fca.org.uk/handbook/conc3/conc3s5

## Oracle and fixture evidence

For every financial assertion identify an independently approved golden quote or reference
calculator, its version, effective date, applicable product, input fixture and expected fields.
Keep this metadata in Input fixtures/scenario context, outside the approved request body.
Record currency, units, decimal scale, rounding stage/mode and field-specific tolerances.
A tolerance cannot be silently widened after a mismatch. Fail on missing mapped fields,
nulls or wrong types; do not coerce missing money to zero. Reject NaN/infinity in numeric
oracles. Never derive expected values by copying the system-under-test response or by asking
an LLM to invent a payment, tax or APR value. Reconciliation identities must state included
components and must not double-count final payments, fees, contributions or deposits.

## Framework implementation

Preserve existing scenarios and build the complete shared workspace folder layout. Generate
scenario-scoped typed context, request builders, services, input fixtures, executable bindings
and assertions together. Use System.Net.Http.HttpClient for C# APIs; API-only packs need no
Playwright. Keep branching in strategies/services and out of step definitions. Keep decimal
precision through fixture parsing, serialization, response parsing and assertions. Isolate
responses for repeated requests; support cancellation and bounded timeouts. Do not retry a
quotation submission unless its approved retry semantics allow it.

Resolve ProductId and wire values through approved mappings, never catalogue-name guesses.
Quote dates, customer type, maintenance and pricing versions cannot be appended to the current
request body. When a risk needs an unavailable control, document the contract/configuration gap
and retain its traceability instead of fabricating an executable scenario.

## Evaluation and triage

Keep requirement ID, case ID and Scenario Outline row linked to the input/oracle versions,
actual assertion evidence, runner output, target environment and generated pack revision.
An HTTP success is transport evidence, not proof of correct financial calculations. Compilation,
static review, repository smoke tests and synthetic data generation do not establish execution
of a generated pack. Run that pack through its configured BDD runner and inspect discovered,
executed, failed, skipped and not-run cases, including every Examples row.

Classify an observed financial mismatch against a valid oracle as failed. Classify missing
credentials, oracle, contract mapping or unavailable target as blocked/not-run as appropriate;
do not invent product defects from setup failures. Distinguish pricing-version drift and stale
fixtures from implementation defects, preserving actual evidence for review. Do not mark a
blocked financial assertion passed because another assertion or the HTTP request passed.
Retain bounded, redacted expected/actual differences and correlation evidence; keep secrets and
customer data out of downloadable reports. Human approval of business semantics remains distinct
from model-generated suggestions and observed execution outcomes.
