# Auto Finance automation policy

Generate API-focused executable Gherkin for `/api/v1/quotes`, quote retrieval, recalculation, and
cancellation/status changes. Use Scenario Outlines with Examples for finance-product terms,
deposits, mileage, prices, status codes, business error codes, promotions, and downstream failure
matrices. Assertions must cover calculation outputs and traceability without guessing unapproved
APR or regulatory formulas. Include contract, security, idempotency, concurrency, resilience, and
the two-second performance objective where relevant.

Keep every Scenario and Scenario Outline concise: target exactly three executable step lines—one
`Given`, one `When`, and one `Then`. A fourth `And` or `But` step is permitted only when essential.
Never emit more than four executable step lines. Examples-table rows do not count as steps.
Keep the text after each step keyword at 100 characters or fewer. Express one business condition,
one action, or one observable outcome per line. Put input combinations in the Examples table and
keep calculation detail in structured test data rather than listing it inside a Gherkin step.
