# Auto Finance Quotation Service profile

Use the version-controlled Quotation Service BRD baseline in this profile as the authoritative
business knowledge source for test design. Preserve its `BR-*` and `NFR-*` identifiers and do not
invent finance formulas, eligibility thresholds, regulatory wording, rounding policy, or product
rules that the BRD leaves for Finance Product, Legal, or Compliance approval.

Prioritize calculation correctness, product eligibility, monetary boundaries, promotion validity,
quote lifecycle, authentication and authorization, downstream resilience, auditability,
idempotency, concurrency isolation, performance, and regulatory disclosures. Use GBP and decimal
monetary representations for the initial implementation. Treat credit checks, KYC, AML, payment
collection, loan creation, contract signing, delivery, Direct Debit, collections, and full finance
application submission as out of scope.
