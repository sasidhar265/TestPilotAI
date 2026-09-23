@api
Feature: Quality Lifecycle Studio API
  As a quality engineer
  I want stable API contracts
  So that generated test evidence can be integrated into CI

  Scenario: TC-API-001 - Return HTTP 200 and identify FastAPI in the health response
    Given the Quality Lifecycle Studio is available
    When I request the health endpoint
    Then the response status is 200
    And the health response identifies the FastAPI runtime

  Scenario: TC-API-002 - Reject a generation request with a description that is too short
    Given the Quality Lifecycle Studio is available
    When I submit a generation request with description "too short"
    Then the response status is 422
