@automation @generation
Feature: Generate structured test cases from requirements
  As a quality engineer
  I want requirements converted into validated test cases
  So that I can start test design from a consistent, traceable draft

  Background:
    Given the Quality Lifecycle Studio API is available

  @smoke @FR-001 @FR-004 @FR-005
  Scenario Outline: Generate cases from valid pasted requirement text
    Given a synthetic requirement containing <length> characters
    And the requested output format is "normal"
    When the client submits the requirement to "/api/generate"
    Then the response status is 200
    And every returned case has an ID, title, objective, category, priority, execution mode, feasibility reason, and observable steps

    Examples:
      | length |
      | 10     |
      | 500    |
      | 30000  |

  @negative @FR-001 @FR-014
  Scenario Outline: Reject requirement text outside the allowed boundary
    Given a synthetic requirement containing <length> characters
    When the client submits the requirement to "/api/generate"
    Then the response status is 422
    And the response contains an actionable validation error without requirement content or credentials

    Examples:
      | length |
      | 9      |
      | 30001  |

  @bdd @FR-006
  Scenario: Generate copy-ready SpecFlow BDD output
    Given a valid synthetic requirement
    And the requested output format is "bdd"
    When the client submits the requirement to "/api/generate"
    Then the response status is 200
    And each automated case contains valid Given, When, and Then Gherkin
    And every scenario has an observable outcome

  @validation @FR-007 @FR-008
  Scenario: Do not store a newly generated suite that fails independent validation
    Given generation returns a suite with a validation error
    When the multi-agent pipeline validates the suite
    Then the validation result is failed with actionable findings
    And the storage agent is not called for that suite

  @memory @FR-009 @FR-010
  Scenario: Reuse and revalidate an exact matching approved suite
    Given an approved suite exists for a normalized requirement and generation options
    When the same normalized request is submitted again
    Then no new Copilot generation request is made
    And the retrieved suite is independently revalidated before it is returned
    And the generation source is "organizational-memory"
