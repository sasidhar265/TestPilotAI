@ui
Feature: Quality Lifecycle Studio workspace
  As a quality engineer
  I want the workspace to expose the governed test-generation flow
  So that UI automation can verify the reviewer experience

  Scenario: TC-UI-001 - Display the generation form and disable Generate until requirements are entered
    Given the Quality Lifecycle Studio is available
    When I open the workspace in a browser
    Then the page title contains "Auto Finance Quality"
    And the generation form is visible
    And the generation submit button is disabled until requirements are supplied

  Scenario: TC-UI-002 - Display the Automation option and model selector
    Given the Quality Lifecycle Studio is available
    When I open the workspace in a browser
    Then the generation target includes "Automation"
    And the model selector is visible
