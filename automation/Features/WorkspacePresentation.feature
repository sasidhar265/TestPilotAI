Feature: Consistent workspace presentation
  Main workspace pages load shared presentation and retain their heading and cache contracts.

  Scenario Outline: Serve a consistent accessible workspace page
    When I inspect the "<page>" workspace page presentation
    Then the workspace page has shared styles and navigation with one main heading

    Examples:
      | page          |
      | index         |
      | documentation |
      | knowledge     |
      | logs          |
      | users         |
      | api-docs      |
      | user-guide    |
