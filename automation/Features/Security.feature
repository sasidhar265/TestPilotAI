@security
Feature: Quality Lifecycle Studio security controls
  As a security-conscious QA engineer
  I want protected operations and safe transport behavior
  So that test data and provider credentials are not exposed

  Scenario: Protected generation endpoint rejects an absent bearer token
    Given the Quality Lifecycle Studio is available
    And API authentication is configured
    When I submit a generation request without credentials
    Then the response status is 401

  Scenario: Health responses never expose provider credentials
    Given the Quality Lifecycle Studio is available
    When I request the health endpoint
    Then the response must not contain a provider secret
