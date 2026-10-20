Feature: Updated BRD after BA review
  Human finding decisions create a new source version and trigger exact-source revalidation.

  Scenario: Pending findings cannot be silently incorporated into a revised BRD
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    Then pending suggestions prevent creating an updated BRD

  Scenario Outline: Human decisions determine the updated BRD and trigger fresh validation
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    And the BA records the finding action "<action>"
    And the BA creates the updated BRD and requests revalidation
    Then the updated BRD reflects the "<action>" decision and preserves the original
    And the updated BRD has fresh assessments without automatic approval
    And the previous review cannot overwrite the updated BRD

    Examples:
      | action  |
      | accept  |
      | edit    |
      | reject  |
      | clarify |

  Scenario: Open feedback requests remain explicit blockers after revalidation
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    And the BA records the finding action "clarify"
    And the BA creates the updated BRD and requests revalidation
    Then open feedback requests block signoff of the updated BRD
