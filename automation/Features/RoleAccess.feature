@api @role-access
Feature: Role specific workspace authorization
  Accounts expose their assigned landing page and testing capabilities and enforce them on API calls.

  Scenario Outline: Authorized and restricted operations follow the assigned role
    Given an isolated account using role fixture "<fixture>"
    When I exercise its permitted and restricted operations
    Then its profile and operation responses match the role fixture

    Examples:
      | fixture        |
      | ba             |
      | functional     |
      | automation     |
      | non-functional |
      | lead           |
      | admin          |

  Scenario Outline: Changing an account role revokes its existing session
    Given an isolated account using role fixture "<fixture>"
    When an administrator changes its assigned role
    Then its existing browser session is rejected

    Examples:
      | fixture        |
      | ba             |
      | functional     |
      | automation     |
      | non-functional |
      | lead           |
      | admin          |
