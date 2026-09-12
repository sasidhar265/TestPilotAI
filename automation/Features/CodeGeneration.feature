@api
Feature: Code generation approval
  Code generation uses the current Quality Gate report and rejects inconsistent approval.

  Scenario: Failed design validation prevents implementation generation
    Given the Quality Lifecycle Studio is available
    When I request an automation pack with "failed" design validation
    Then the response status is 422
    And code generation reports "Quality Gate-approved"

  Scenario: Passing reports cannot contain validation errors
    Given the Quality Lifecycle Studio is available
    When I request an automation pack with "inconsistent" design validation
    Then the response status is 422
    And code generation reports "inconsistent"

  Scenario: A current passing report allows a complete pack despite historical notes
    Given the Quality Lifecycle Studio is available
    When I request an automation pack with "passed" design validation
    Then the response status is 200
    And the automation pack contains executable bindings and current input data
