@automation @delivery
Feature: Deliver approved test scenarios safely
  As a quality engineer
  I want to export or explicitly publish selected scenarios
  So that approved test designs can enter downstream workflows

  Background:
    Given a generated suite has passed independent validation

  @FR-011
  Scenario Outline: Export a generated suite
    When the client requests the suite in <format> format
    Then the response status is 200
    And the downloaded artifact contains every test case and its traceability data
    And the response content type matches <format>

    Examples:
      | format |
      | JSON   |
      | CSV    |
      | XLSX   |

  @FR-006 @FR-011
  Scenario: Export automated scenarios as a feature file
    Given the suite contains automated BDD cases
    When the client requests the suite in feature format
    Then the response status is 200
    And the artifact has one Feature header and all automated scenarios
    And the artifact is copy-ready SpecFlow Gherkin

  @FR-012
  Scenario: Publish only explicitly selected cases to Jira
    Given Jira is configured with a synthetic project
    And the user selects cases "TC-001" and "TC-003"
    When the user publishes the selection to existing issue "QA-101"
    Then only "TC-001" and "TC-003" are attached to "QA-101"
    And the result identifies the attachment and whether a comment was added

  @negative @FR-012 @FR-014
  Scenario: Reject a Jira publishing request containing an unknown case ID
    Given the selected case list contains an ID absent from the suite
    When the client submits the publishing request
    Then the request is rejected before contacting Jira
    And the response identifies the invalid selection without exposing credentials

  @FR-013
  Scenario: Discover the configured functional agents
    When the client requests "/api/agents"
    Then the response status is 200
    And every configured agent includes its purpose, runtime, and capabilities
    And the agents are listed in functional execution order

  @NFR-005 @FR-014
  Scenario: Correlate a safe API failure with a request ID
    Given the client supplies request ID "qa-safe-reference-101"
    When an API operation fails
    Then the response includes "X-Request-ID" with value "qa-safe-reference-101"
    And the error is actionable without requirements, prompts, generated content, or credentials

