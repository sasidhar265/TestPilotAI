# Application usage dashboard

Open **Quality Lifecycle → Application usage** for shared workspace totals. Filter by the last 7, 30 or 90 days, or all recorded activity. Refresh fetches persisted server data; navigation and suite completion refresh the view automatically.

Manual and automation counts represent generated output, including revisions, expansions and validation-failed suites. These are not unique approved-case counts. Memory reuse is shown separately. The dashboard retains the existing suite traceability report below usage.

Generation counters and model calls persist in `usage.db` beside the configured organizational memory database. Existing retained generation records are imported idempotently from `dashboard.db`. Previously pruned records cannot be reconstructed. Future usage is not limited to the 200-action dashboard history.

New OpenAI and Gemini responses, Copilot SDK usage events and Codex CLI completion events supply token counts. Retries and artifact generation are included. No prompts, responses, credentials or test content are stored in the usage ledger. Historical tokens, failed calls without usage metadata and provider activity outside this application are unavailable. Providers that omit usage metadata cannot be treated as zero usage.

The USD estimate currently supports standard OpenAI GPT-5.4 and its 2026-03-05 snapshot on the official default API endpoint. Rates were verified on 2026-09-19: $2.50 input, $0.25 cached input and $15.00 output per million tokens. Input above 272,000 tokens doubles input rates and multiplies output rates by 1.5. Rates are captured at recording time; changing the rate table does not reprice history.

Source: https://developers.openai.com/api/docs/models/gpt-5.4

Custom API endpoints, non-standard service tiers, other models, Gemini, Copilot and Codex subscription routes show **Not priced**. No API-equivalent cost is presented as a subscription charge. Partial subtotals exclude unpriced calls. Taxes, tools, negotiated rates and subscriptions are excluded. The dashboard is an application usage estimate, not a provider invoice.

Restart the application after deploying to start recording usage. Back up `usage.db` alongside the other workspace databases.
