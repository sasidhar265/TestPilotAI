Feature: Understand the requested task outcome
  The orchestrator selects an artifact from the input instead of always generating stories.

  Scenario Outline: <caseId> - Select the requested artifact semantically
    Given the Quality Lifecycle Studio is available
    When I interpret the "<fixture>" task prompt
    Then the response status is 200
    And the selected task workflow is "<workflow>"

    Examples:
      | caseId        | fixture              | workflow          |
      | TC-INTENT-001 | framework-paraphrase | website-framework |
      | TC-INTENT-002 | test-cases           | test-cases        |

  Scenario: TC-INTENT-003 - Ask what to produce for a bare requirement
    Given the Quality Lifecycle Studio is available
    When I interpret the "ambiguous" task prompt
    Then the response status is 200
    And the selected task workflow is "clarify"
    And the task interpretation asks for clarification
