@api
Feature: Code generation approval
  Code generation uses the current Quality Gate report and rejects inconsistent approval.

  Scenario: TC-CODE-001 - Reject automation pack generation when design validation fails
    Given the Quality Lifecycle Studio is available
    When I request an automation pack with "failed" design validation
    Then the response status is 422
    And code generation reports "Quality Gate-approved"

  Scenario: TC-CODE-002 - Reject a passing validation report that contains errors
    Given the Quality Lifecycle Studio is available
    When I request an automation pack with "inconsistent" design validation
    Then the response status is 422
    And code generation reports "inconsistent"

  Scenario: TC-CODE-003 - Generate an executable pack when current validation passes despite historical notes
    Given the Quality Lifecycle Studio is available
    When I request an automation pack with "passed" design validation
    Then the response status is 200
    And the automation pack contains executable bindings and current input data
