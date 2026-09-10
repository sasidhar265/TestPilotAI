# Feature file standards

Edit this file to define the team's conventions for generated Gherkin.

- Do not emit tags at any level: no feature, scenario, outline, or examples tags.
- Use concise business language and descriptive Feature and Scenario names.
- Keep each scenario focused on one observable outcome.
- Use Given for setup, When for the action, Then for the observable result.
- Use no more than four steps per scenario and 100 characters per step text.
- Use Scenario Outline and Examples for data-driven cases; keep all placeholders in Examples.
- Extract shared setup into Background where appropriate.
- Keep test IDs and requirement mappings in suite metadata, not Gherkin tags.
