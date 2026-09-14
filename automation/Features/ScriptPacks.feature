Feature: Performance and database script packs
  Validated test cases retain explicit request and query mappings in native script packs.

  Scenario Outline: Generate traceable native scripts
    Given the Quality Lifecycle Studio is available
    When I generate the "<fixture>" script pack
    Then the response status is 200
    And the script pack includes "<file>" containing "<content>"
    And the script pack preserves its input case mappings

    Examples:
      | fixture | file                     | content                 |
      | jmeter  | Features/performance.jmx  | DurationAssertion       |
      | sql     | Features/database.sql    | actual_rows             |
      | oracle  | Features/database.sql    | RAISE_APPLICATION_ERROR |

  Scenario Outline: Download native scripts with their inputs
    Given the Quality Lifecycle Studio is available
    When I download the "<fixture>" script pack
    Then the response status is 200
    And the script archive includes "<file>"

    Examples:
      | fixture | file                    |
      | jmeter  | Features/performance.jmx |
      | sql     | Features/database.sql   |
      | oracle  | Features/database.sql   |

  Scenario Outline: Reject incomplete or unapproved mappings
    Given the Quality Lifecycle Studio is available
    When I generate the "<fixture>" script pack
    Then the response status is 422
    And the workflow response contains "<reason>"

    Examples:
      | fixture        | reason                 |
      | missing        | at least one           |
      | unknown-case   | every selected         |
      | duplicate-case | every selected         |
      | failed-gate    | Quality Gate-approved  |
      | invalid-query  | one SELECT             |
