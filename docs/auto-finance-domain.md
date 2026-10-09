# Auto-finance domain pack and calculation tools

The domain pack is independent of organisational memory. It does not enable memory storage,
read the old plaintext knowledge database, migrate records or change mandatory LLM models.

## Configure the domain pack

`workspace/runtime-config.toml` controls `auto_finance_domain_enabled` and
`auto_finance_domain_path`. Restart after changing those settings. The domain TOML is reloaded
on each request, so edits to its catalogue/rules/mappings take effect without restart.

`workspace/auto-finance-domain.toml` contains products, journey reference templates,
market/currency, minor-unit precision and rounding. The supplied product names match the
existing explorer. They are reference labels, not approved product contracts. The market is
`unspecified` until the owner supplies it. Currency defaults to GBP and is configurable.
No rates, credit thresholds, eligibility decisions, statutory limits or tax rates are supplied.

Rules require a BR ID, exact wording, status, version, owner and source. Only `approved` rules
matching an explicitly selected product/journey enter the governing request. Drafts are
reference-only. Conflicting rule wording and unknown references fail instead of choosing a
precedence. Existing shared business rules remain authoritative and cannot be overwritten by
the domain pack. Missing policy is left for the owner, rather than inferred from journey focus.

Select **Product context** and **Journey context** in the Quality workspace. The scope follows
text generation, uploaded documents and reviewed story/scenario handoffs. Changing scope
invalidates downstream workflow stages. The domain pack is added to additional context, with
approval provenance and reference-only guidance, and applicable approved rules retain their
IDs for `acceptance_criteria_covered`. Quotation request bodies are not changed.

## Calculation validation

Open **Knowledge source → Domain pack & calculation validation**. Supply amounts and a rate
from your system, then optionally enter the observed result. Values use Python Decimal rather
than binary floating-point. A mismatch is reported with expected, observed and difference;
it does not silently replace the observed value or assert product-policy approval.

Choose **Use calculation in generation** to attach its supplied inputs to the next request.
The server recomputes the result and puts the reference values and conventions in domain context.
It never trusts a browser-supplied expected result. Clear calculation context in the Quality
workspace when the values no longer apply. Inputs are staged in browser session storage only
when you choose this action; no organisational memory is enabled by it.

Three calculations are provided:

- **Amount financed:** cash price minus deposit plus explicitly financed fees. Upfront fees
  belong outside the principal. Deposit cannot exceed cash price.
- **Monthly annuity with a balloon:** monthly payments in arrears, a fixed nominal annual
  interest rate divided by 12, and the supplied balloon paid alongside the final regular
  instalment. Each period's interest is rounded using the configured convention; the last
  regular instalment is adjusted so the balance reaches the supplied balloon. Total repayments
  include regular instalments and the balloon. Customer total payable also includes supplied
  deposit and upfront fees.
- **Net/VAT/gross:** supplied net amount times the supplied VAT percentage; rounded VAT plus
  net equals gross. The tool does not infer tax applicability or the applicable rate.

Amounts must match configured currency precision. Rates can have up to eight decimal places.
Zero nominal interest has its own division formula, terms are limited to 1–600 payments,
and negative amounts, oversized balloons and unknown observed fields are rejected.
Observed comparison is exact; there is no hidden financial tolerance.

The annuity is the standard constant-payment mathematical convention described in
[Microsoft's PMT documentation](https://support.microsoft.com/en-us/Excel/functions/pmt-function).
Its nominal rate is not statutory APR. For the distinction between the loan rate and APR,
see [CFPB's explanation](https://www.consumerfinance.gov/ask-cfpb/what-is-the-difference-between-a-loan-interest-rate-and-the-apr-en-733/).
These sources explain arithmetic/terminology; they do not establish jurisdiction-specific
product rules for this pack.

The tools do not implement an approved lender pricing engine, flat-rate calculations,
irregular cashflows, compounding conventions other than the declared model, statutory APR,
early settlement, rebates, amortisation fees or credit decisions. Those require explicit
approved product-specific methods and independent expected examples before implementation.

## Domain traceability graph

Graph and Tree graph include a reference-domain root, products, journeys and versioned rules.
Catalogue edges are labelled as references. Add explicit `mappings` in the domain TOML using
project, requirement key, **requirement version**, product, journeys and rule IDs. No graph
relationships are inferred by searching names or descriptions.

A rule-to-test coverage edge requires all of: an approved rule, a versioned requirement mapping,
the requirement pinned in the suite baseline, the suite's test-to-requirement mapping, and the
exact BR ID in the case's `acceptance_criteria_covered`. Existing test/result/defect links then
allow following the rule to execution evidence. Draft rules do not establish coverage.
The graph displays the current configured rule version; a link is traceability, not proof
that a previous execution tested a subsequently edited rule. Keep approved versions stable.

## API and verification

Authenticated `GET /api/finance/domain-pack` returns the validated reference catalogue.
`POST /api/finance/calculations` uses a discriminated `kind`: `annuity`, `principal`, or `vat`.
Request amounts and observed values can be decimal strings; responses contain decimal strings.
The calculation response includes conventions, precision, rounding, results and optional checks.
Invalid input returns 422; a disabled/unreadable domain pack returns 503.

Live API scenarios are in `automation/Features/AutoFinance.feature` with executable C#
bindings, a typed HttpClientFactory client, request builder, models, service and input vectors
in the shared automation layout. `Input/FinanceCalculations.Json` contains explicitly synthetic,
mathematically specified vectors for the reference calculator. They are not quotation requests,
approved credit/pricing rules or production customer data. The approved quotation fixture is
unchanged. The default ReqnRoll project discovers these scenarios alongside existing features.

For an isolated run in your configured environment:

```bash
QUALITY_LIFECYCLE_BASE_URL=http://127.0.0.1:8000 \
API_AUTH_TOKEN="$API_AUTH_TOKEN" \
dotnet test automation/QualityLifecycle.Automation.csproj \
  --filter FullyQualifiedName~AutoFinance \
  --logger 'trx;LogFileName=AutoFinance.trx' \
  --results-directory automation/TestResults/Reports/AutoFinance
```

A signed `API_SESSION_COOKIE` is also supported; keep it outside tracked files.
The fixture expectations assume the supplied GBP/two-decimal/half-up test configuration.
Use a separately configured test app when your deployment has different precision or rounding.
