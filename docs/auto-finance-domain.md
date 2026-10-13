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

## Domain knowledge library

Auto finance → **UK domain guide** opens `/auto-finance-guide` within the shared workspace,
preserving navigation and workflow drafts. It embeds `app/static/auto-finance-uk.html`, a self-contained
reference with an interactive conceptual graph, product/use-case comparisons, official UK
brand/provider examples, the vehicle-to-contract journey, financial terminology, source links
and a signing checklist. Download HTML preserves the inline styles and scripts for offline
reading; print expands the guide. No checklist data is submitted or persisted.
Only the guide permits same-origin framing, and its exact inline script is allowed by a
content hash; other pages retain their existing framing and script restrictions.
**Download PDF** serves `app/static/auto-finance-uk.pdf`: an A4 document with a cover,
page-numbered contents, running headers/footers, section bookmarks and clickable references.
Rebuild it after guide edits with `.venv/bin/python tools/export_auto_finance_guide.py`
in a development environment with Playwright and Chromium installed. Browser rendering is
required only to build the file, not when users download it. The PDF metadata records the
source HTML SHA-256 fingerprint for freshness checks.
The guide is public-source reference material, not a live pricing catalogue or approved policy.
It is not automatically loaded into agent prompts and does not alter the configured market,
approved rule catalogue, source baseline or saved coverage graph. Promotion into agent context
and approved requirements follows the existing owner/source/version governance workflow.

Knowledge → Auto finance → Domain pack now lists and searches the configured profile's
Markdown knowledge documents, including the original quotation BRD/catalogue/risk material.
The same files are loaded into agent prompts, independently of organisational memory.

The auto-finance-quotation profile includes product distinctions, lifecycle analysis,
calculation/data evidence and a governance/approval backlog. Each new document identifies
version, reference status, review date, scope, sources and responsible review functions.
Lifecycle guidance applies only to explicitly requested journeys and does not widen the
quotation BRD's scope. Public-source material is reference-only.

Follow auto-finance-governance-and-gaps.md to promote reviewed source material into the
business baseline, approved domain rules and explicit requirement mappings. No owner,
policy threshold, pricing oracle or business approval has been invented. The baseline and
approved rule lists remain empty until the accountable owners provide approved material.

## Generation context visibility

The Quality workspace includes **Knowledge and considerations** with a manual preview action.
Before BA review, alignment validation, story, scenario and test-case calls, the UI requests
`POST /api/workflow/knowledge-context` with the stage and source request. It shows the profile
reference topics and section guidance, selected domain product/journey focus, calculation
conventions/results, exact approved domain/shared/request rules, and effective approved sources.
The preview calls no model and grants no approval. It records preparation time and source,
request and context fingerprints. Stage snapshots remain visible for review during the session;
editing requirements or options marks earlier snapshots as historical. They are not persisted
as execution evidence or attached to exported artifacts.

Delivery is stage-specific: scenario generation receives reviewed stories and scoped request
context, not the full library directly. The preview describes context available before the call,
not model reasoning or proof that every topic influenced output. Configuration can change between
preview and generation; validation and artifact evidence remain separate. Preview failures are
shown and do not replace the existing generation/alignment gates.

## Live agent activity

The generation dialog and background panel show the latest backend agent/action and a timestamped
activity timeline. Knowledge preview requests do not take over the active generation feed.
Provider execution reports the selected route/model, real elapsed waiting every ten seconds,
response arrival, repair and fallback attempts, and stage validation. The activity stream records
execution status and safe summaries, not prompts, customer data, generated payloads or internal
model reasoning. Feed connection errors and completed requests with no reported activity are
shown explicitly. Activity is process-local and bounded; a server restart clears it.

## Selected AI provider

The AI provider selected in Requirements is passed through BA review, approved-source alignment,
stories, scenarios, test cases and automation-pack generation. Explicit Codex, OpenAI API, Gemini
and Copilot selections use only that provider; repairs remain on the same provider and access
failures are reported rather than silently switching to Copilot. Only `auto-fallback` retains
the configured Copilot → OpenAI API → Gemini API → Codex route. Copilot uses `claude-haiku-4.5`;
Codex uses `gpt-6-astra`. OpenAI API and Gemini use their configured models. Reusing a validated
local artifact does not invoke any provider.

Explicit non-Copilot test-case requests use local governed coordination, avoiding a hidden
Copilot coordinator call. Validation and storage controls still apply to the generated suite.

## Validation evidence in the popup

BA review publishes its deterministic evidence checks (review-area completeness, BRD quote
and knowledge-citation grounding, and unchanged knowledge fingerprint) using the same
validation event contract as stories, scenarios and the Quality Gate. Sources distinguish
verified citations from available but uncited references. Passing these checks does not grant
business approval or establish regulatory compliance, financial correctness or test execution.

When live checkpoints are unavailable, the UI can show the returned BA outcome or suite
validation report, explicitly identified as response data. The final suite report takes
precedence over an earlier repair failure. Completed operations never retain an indefinite
waiting message: missing validation evidence and missing source references are stated directly.
