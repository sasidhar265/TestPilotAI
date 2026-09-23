@api
Feature: Five-stage requirement handoffs
  Requirements retain their source and story ownership before test case generation.

  Scenario: TC-FLOW-001 - Accept reviewed stories linked to source requirements
    Given the Quality Lifecycle Studio is available
    When I validate the "approved-stories" workflow handoff
    Then the response status is 200
    And the workflow response contains "ST-001"

  Scenario: TC-FLOW-002 - Reject stories without supporting source requirements
    Given the Quality Lifecycle Studio is available
    When I validate the "ungrounded-stories" workflow handoff
    Then the response status is 422
    And the workflow response contains "source requirements"

  Scenario: TC-FLOW-003 - Accept reviewed scenarios linked to their stories
    Given the Quality Lifecycle Studio is available
    When I validate the "approved-scenarios" workflow handoff
    Then the response status is 200
    And the workflow response contains "SC-001"

  Scenario: TC-FLOW-004 - Reject scenarios linked to an unknown story
    Given the Quality Lifecycle Studio is available
    When I validate the "orphan-scenarios" workflow handoff
    Then the response status is 422
    And the workflow response contains "unknown story"
