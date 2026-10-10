Feature: BA agent BRD input validation
  Invalid input and forged upload receipts never become business review evidence.

  Scenario Outline: Reject an invalid BA review source
    When I submit the BA review fixture "<fixture>"
    Then the BA agent rejects the invalid BRD without a review outcome

    Examples:
      | fixture             |
      | missing-description |
      | short-description   |
      | forged-upload       |
