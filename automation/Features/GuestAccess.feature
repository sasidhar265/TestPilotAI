Feature: Guest preview confidentiality
  Guests can preview the workspace without reading customer requirements or execution evidence.

  Scenario Outline: Guest requests cannot expose protected workspace data
    Given I have entered the temporary guest preview
    When the guest requests protected "<resource>" using "<method>"
    Then the guest response status is 403

    Examples:
      | resource  | method |
      | progress  | GET    |
      | dashboard | GET    |
      | history   | GET    |
      | history   | HEAD   |
      | report    | GET    |
      | report    | HEAD   |
      | rules     | GET    |
      | standards | GET    |
      | knowledge | GET    |

  Scenario: Guest preview remains available without exposing workspace data
    Given I have entered the temporary guest preview
    When the guest opens the static workspace preview
    Then the guest response status is 200
