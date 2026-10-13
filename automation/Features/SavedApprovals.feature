Feature: Saved approval visibility
  Explicitly approved test artifacts remain visible independently of AI reuse.

  Scenario: TC-SAVED-001 - Approved tests appear in Saved outputs and Project dashboard
    Given the Quality Lifecycle Studio is available
    When I approve the stored health test fixture
    Then the response status is 200
    And the approved artifact is visible in saved outputs and project records
    And the saved artifact includes only the approved test cases
