@security
Feature: Quality Lifecycle Studio security controls
  As a security-conscious QA engineer
  I want protected operations and safe transport behavior
  So that test data and provider credentials are not exposed

  Scenario: TC-SEC-001 - Reject generation without authentication with HTTP 401
    Given the Quality Lifecycle Studio is available
    And API authentication is configured
    When I submit a generation request without credentials
    Then the response status is 401

  Scenario: TC-SEC-002 - Exclude provider secrets from the health response
    Given the Quality Lifecycle Studio is available
    When I request the health endpoint
    Then the response must not contain a provider secret
