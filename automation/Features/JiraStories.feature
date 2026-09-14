Feature: Jira story approval boundary
  Only selected stories with reviewer approval can reach Jira.

  Scenario Outline: Reject invalid story publication before contacting Jira
    Given the Quality Lifecycle Studio is available
    When I publish the "<fixture>" approved story selection to Jira
    Then the response status is 422
    And the workflow response contains "<reason>"

    Examples:
      | fixture         | reason              |
      | jira-unapproved | must be approved    |
      | jira-unknown    | Unknown selected    |
      | jira-duplicate  | must be unique      |
      | jira-reviewer   | at least 2          |
