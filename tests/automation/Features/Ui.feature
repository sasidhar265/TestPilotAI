@ui
Feature: Quality Lifecycle Studio workspace
  As a quality engineer
  I want the workspace to expose the governed test-generation flow
  So that UI automation can verify the reviewer experience

  Scenario: Workspace loads its guarded generation controls
    Given the Quality Lifecycle Studio is available
    When I open the workspace in a browser
    Then the page title contains "Quality Lifecycle Studio"
    And the generation form is visible
    And the generation submit button is disabled until requirements are supplied

  Scenario: Workspace offers automation-oriented generation
    Given the Quality Lifecycle Studio is available
    When I open the workspace in a browser
    Then the generation target includes "Automation"
    And the model selector is visible
