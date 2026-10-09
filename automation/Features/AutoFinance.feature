Feature: Auto finance domain references and deterministic calculations
  Reference arithmetic uses explicitly supplied synthetic values and declared conventions.
  These scenarios do not submit quotations or establish product pricing or regulatory rules.

  Scenario: TC-FINANCE-001 - Load the configured reference domain catalogue
    Given the Quality Lifecycle Studio is available
    When I request the auto finance domain catalogue
    Then the auto finance catalogue identifies reference content and valid mappings

  Scenario Outline: TC-FINANCE-002 - Reconcile deterministic calculations and observed values
    Given the Quality Lifecycle Studio is available
    When I validate the auto finance fixture "<fixture>"
    Then the auto finance result matches its fixture expectations
    Examples:
      | fixture          |
      | zero_interest    |
      | balloon          |
      | nominal_interest |
      | rounding         |
      | mismatch         |
      | principal        |
      | vat              |

  Scenario Outline: TC-FINANCE-003 - Reject invalid inputs and unsupported expectations
    Given the Quality Lifecycle Studio is available
    When I validate the auto finance fixture "<fixture>"
    Then the auto finance result matches its fixture expectations
    Examples:
      | fixture               |
      | invalid_deposit       |
      | invalid_term          |
      | unsupported_apr       |
      | extra_contract_fields |
