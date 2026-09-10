@api
Feature: Quality Lifecycle Studio API
  As a quality engineer
  I want stable API contracts
  So that generated test evidence can be integrated into CI

  Scenario: Health endpoint reports the configured runtime
    Given the Quality Lifecycle Studio is available
    When I request the health endpoint
    Then the response status is 200
    And the health response identifies the FastAPI runtime

  Scenario: Short generation requests are rejected before provider execution
    Given the Quality Lifecycle Studio is available
    When I submit a generation request with description "too short"
    Then the response status is 422
