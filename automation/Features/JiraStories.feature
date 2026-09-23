Feature: Jira story approval boundary
  Only selected stories with reviewer approval can reach Jira.

  Scenario Outline: <caseId> - Reject Jira publication when <condition>
    Given the Quality Lifecycle Studio is available
    When I publish the "<fixture>" approved story selection to Jira
    Then the response status is 422
    And the workflow response contains "<reason>"

    Examples:
      | caseId | fixture | reason | condition |
      | TC-JIRA-001 | jira-unapproved | must be approved | reviewer approval is missing |
      | TC-JIRA-002 | jira-unknown | Unknown selected | a selected story is unknown |
      | TC-JIRA-003 | jira-duplicate | must be unique | selected stories are duplicated |
      | TC-JIRA-004 | jira-reviewer | at least 2 | the reviewer name is too short |
