# Auto Finance quality-gate policy

Reject output that contradicts the amount-financed formula, applies expired promotions, permits
unsupported terms, omits mandatory PCP mileage, crosses customer data between concurrent quotes,
exposes sensitive financial data in logs, or treats out-of-scope credit/KYC/AML/application
capabilities as Quotation Service behavior. Require explicit mappings to applicable BRD rules and
flag calculations requiring unconfirmed Finance Product or Compliance formulas as assumptions.
For automation Gherkin, require Given, When, and Then, target three executable step lines, and
reject any Scenario or Scenario Outline containing more than four executable step lines. Do not
count Examples-table rows as steps.
Reject Gherkin when the text after any Given, When, Then, And, or But keyword exceeds 100
characters. Prefer short business language; detailed values belong in test data or Examples.
