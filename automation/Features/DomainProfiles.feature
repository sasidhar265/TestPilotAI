Feature: Domain profile configuration
  Shared domain guidance can be configured without changing source files or model policy.

  Scenario: Saving a profile does not activate it automatically
    When I create a custom domain profile
    Then the domain profile response status is 201
    And the original domain profile remains selected

  Scenario: Profile selection applies to new requests without a restart
    When I create a custom domain profile
    And I apply the custom domain profile
    Then the domain profile response status is 200
    And new requests use the custom profile with finance context disabled

  Scenario: Built-in profile policies cannot be overwritten
    When I submit the "builtin" invalid domain profile
    Then the domain profile response status is 409

  Scenario: Profile configuration cannot override model policy
    When I submit the "model" invalid domain profile
    Then the domain profile response status is 422

  Scenario: Invalid approval source metadata is rejected
    When I submit the "baseline" invalid domain profile
    Then the domain profile response status is 422

  Scenario: Concurrent profile edits are rejected
    When I create a custom domain profile
    And I update the domain profile with a stale revision
    Then the domain profile response status is 409

  Scenario: Concurrent selection changes are rejected
    When I create a custom domain profile
    And I apply the custom domain profile
    And I apply a domain selection with a stale revision
    Then the domain profile response status is 409

  Scenario: Anonymous profile configuration is rejected
    When I create a domain profile without authentication
    Then the domain profile response status is 401
