Feature: Performance and database script packs
  Validated test cases retain explicit request and query mappings in native script packs.

  Scenario Outline: <caseId> - Generate <fixture> scripts with assertions and input case mappings
    Given the Quality Lifecycle Studio is available
    When I generate the "<fixture>" script pack
    Then the response status is 200
    And the script pack includes "<file>" containing "<content>"
    And the script pack preserves its input case mappings

    Examples:
      | caseId | fixture | file | content |
      | TC-SCRIPT-001 | jmeter | Features/performance.jmx | DurationAssertion |
      | TC-SCRIPT-002 | sql | Features/database.sql | actual_rows |
      | TC-SCRIPT-003 | oracle | Features/database.sql | RAISE_APPLICATION_ERROR |

  Scenario Outline: <caseId> - Download <fixture> scripts with input files
    Given the Quality Lifecycle Studio is available
    When I download the "<fixture>" script pack
    Then the response status is 200
    And the script archive includes "<file>"

    Examples:
      | caseId | fixture | file |
      | TC-SCRIPT-004 | jmeter | Features/performance.jmx |
      | TC-SCRIPT-005 | sql | Features/database.sql |
      | TC-SCRIPT-006 | oracle | Features/database.sql |

  Scenario Outline: <caseId> - Reject script generation when <condition>
    Given the Quality Lifecycle Studio is available
    When I generate the "<fixture>" script pack
    Then the response status is 422
    And the workflow response contains "<reason>"

    Examples:
      | caseId | fixture | reason | condition |
      | TC-SCRIPT-007 | missing | at least one | request mappings are missing |
      | TC-SCRIPT-008 | unknown-case | every selected | a mapped case is unknown |
      | TC-SCRIPT-009 | duplicate-case | every selected | case mappings are duplicated |
      | TC-SCRIPT-010 | failed-gate | Quality Gate-approved | the Quality Gate has failed |
      | TC-SCRIPT-011 | invalid-query | one SELECT | the query is not a single SELECT |
