@api
Feature: Five-stage requirement handoffs
  Requirements retain their source and story ownership before test case generation.

  Scenario: Reviewed stories preserve their source requirements
    Given the Quality Lifecycle Studio is available
    When I validate the "approved-stories" workflow handoff
    Then the response status is 200
    And the workflow response contains "ST-001"

  Scenario: Stories cannot invent source evidence
    Given the Quality Lifecycle Studio is available
    When I validate the "ungrounded-stories" workflow handoff
    Then the response status is 422
    And the workflow response contains "source requirements"

  Scenario: Reviewed scenarios preserve story ownership
    Given the Quality Lifecycle Studio is available
    When I validate the "approved-scenarios" workflow handoff
    Then the response status is 200
    And the workflow response contains "SC-001"

  Scenario: Scenarios cannot refer to an unknown story
    Given the Quality Lifecycle Studio is available
    When I validate the "orphan-scenarios" workflow handoff
    Then the response status is 422
    And the workflow response contains "unknown story"
