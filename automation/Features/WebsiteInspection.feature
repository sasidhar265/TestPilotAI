Feature: Public website inspection for UI test design
  Observed website evidence is reviewable before entering the existing test generation workflow.

  Scenario: TC-WEB-001 - Inspect the approved CareerPilot public page
    Given the Quality Lifecycle Studio is available
    When I inspect the "careerpilot" website source
    Then the response status is 200
    And the website evidence includes "CareerPilotAI"
    And the website evidence has a signed source and inspection limitations

  Scenario Outline: <caseId> - Reject an unsuitable website target
    Given the Quality Lifecycle Studio is available
    When I inspect the "<fixture>" website source
    Then the response status is 422
    And the workflow response contains "<reason>"

    Examples:
      | caseId | fixture | reason |
      | TC-WEB-002 | loopback | public internet |
      | TC-WEB-003 | file | public HTTP(S) |
      | TC-WEB-004 | credentials | without credentials |
      | TC-WEB-005 | excessive-pages | max_pages |
