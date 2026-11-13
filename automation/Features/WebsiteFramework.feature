Feature: Direct website framework requests
  Website framework prompts use observed public pages without requiring a business BRD.

  Scenario: TC-FRAMEWORK-001 - Build the requested CareerPilot framework directly
    Given the Quality Lifecycle Studio is available
    When I build the "careerpilot" website framework
    Then the response status is 200
    And the website framework is a downloadable Selenium CSharp BDD page object pack

  Scenario Outline: <caseId> - Reject an invalid direct framework request
    Given the Quality Lifecycle Studio is available
    When I build the "<fixture>" website framework
    Then the response status is 422
    And the workflow response contains "<reason>"

    Examples:
      | caseId           | fixture     | reason                     |
      | TC-FRAMEWORK-002 | loopback    | public internet            |
      | TC-FRAMEWORK-003 | credentials | without credentials        |
      | TC-FRAMEWORK-004 | multiple    | one target                 |
      | TC-FRAMEWORK-005 | unsupported | currently support Selenium |
