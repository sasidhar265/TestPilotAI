# Auto finance knowledge governance and approval backlog

Version: 1.0
Status: reference_only — proposed analysis and test-design guidance; business approval pending.
Owner: unassigned; responsible business function identified below must review.
Reviewed: 2026-10-13
Scope: UK-oriented terminology; deployment market remains unspecified.
Authority: existing quotation BRD/profile for project scope; public sources for terminology only.
Do not turn this guidance into governing rules, contract fields or executable financial expectations.
Apply lifecycle material only when explicitly requested; quotation scope remains unchanged.

## Authority and maintenance

Business-approved sources with current effective dates govern business alignment. The Markdown
library is reference guidance. Current explicit requirements and the approved wire contract take
precedence over default examples. Generated artifacts and stored memory are reusable evidence,
not a source of new policy. Public references are terminology and review prompts, not approval.

Review changes through version control. Assign an accountable reviewer, record source/version,
market, product/journey scope and effective/expiry dates. Recheck external sources before policy
approval and whenever regulation or product configuration changes. No automatic approval follows
from publication in this library or successful execution of a test.

## Approval backlog

| Gap | Required deliverable | Responsible function | Current status |
| --- | --- | --- | --- |
| Market and regulatory applicability | Confirm jurisdiction and agreement/customer classifications | Legal / Compliance | Pending; domain market unspecified |
| Product definitions and eligibility | Seven signed product definitions and brand/customer eligibility matrices | Product | Pending |
| Limits and effective configuration | Approved deposit, term, mileage, price, campaign and fallback rules | Product / Pricing | Pending |
| Calculation methods | Product methods, APR, tax, residuals, fees, rounding and tolerances | Finance / Compliance | Pending |
| Independent expected examples | Reviewed synthetic golden examples and oracle provenance | Finance / QA | Pending |
| Lifecycle policy | State transitions, decision matrices, servicing, arrears and settlement methods | Credit Risk / Operations / Collections | Pending |
| Approved business baseline | Source text with accountable approval and effective dates | Business owner | Pending; no effective approved sources supplied |
| Rule traceability | Exact BR wording and explicit project requirement versions | Business owner / QA | Pending; no approved domain rules/mappings supplied |

## Promotion procedure

1. Review the actual source document with the named accountable business function.
2. Add its source text to workspace/requirements-baseline.json with a unique ID, version,
   title, draft/approved status, approved_by, effective_from and expires_on. Leave approval
   empty for drafts; never manufacture an approver. The application only governs against
   effective approved sources.
3. Add exact approved rules to workspace/auto-finance-domain.toml with BR ID, description,
   status, version, owner, source and explicit product/journey scope. Do not copy analysis
   prompts into approved rules. Check conflicts with shared business rules.
4. Add mappings only for real project, requirement key and pinned requirement version.
   Attach BR IDs to test coverage, execute the relevant pack and retain actual results.
5. Re-review generated artifacts after changing policy. Enable organisational memory only
   with the configured encryption secret and retention policy; memory does not grant approval.

The draft quotation baseline can guide generation but cannot satisfy business approval. The
Knowledge domain view exposes the library independently of organisational memory being enabled.
