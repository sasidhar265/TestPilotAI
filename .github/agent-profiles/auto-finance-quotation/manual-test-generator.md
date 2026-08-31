# UK Quotation Services manual-testing policy

This project explicitly requires a manually executable counterpart for every BRD validation in the
profile's Mandatory validation inventory, including all nineteen business error codes. Generate
structured manual cases for positive, negative, missing-value, configured-boundary, and effective-
date behavior where applicable. Use the exact `POST /api/v1/quotations` contract, canonical test
data, expected error schema, and `BR-QT-*` mapping. Set `gherkin` to null.

The manual feasibility reason must state that repeatable human execution and evidence capture are
required for BRD acceptance/release review; do not falsely claim deterministic validation needs
subjective judgment. Every action has an observable expected result, including exact error code,
field when supplied, correlation ID, and confirmation that no stack trace/confidential detail is
shown. Do not sample or omit validation categories when complete BRD coverage is requested.

Also focus manual coverage on FCA Consumer Duty understanding, regulated disclosure clarity, customer
versus business language, VAT net/gross presentation, finance payment versus leasing rental
presentation, final/balloon/GFV and mileage comprehension, commission disclosure where applicable,
brand/product/maintenance naming, audit investigation usability, accessibility, and exploratory
comparison across representative configurations.

Consolidate human review across representative brands while keeping separate charters when
audience, product mechanics, VAT or disclosure duties differ. Do not invent final regulatory
wording; require Compliance-approved expected evidence. Deterministic validations are included
here only because this profile explicitly requires manual acceptance coverage in addition to
automation; they remain primary automation candidates.
