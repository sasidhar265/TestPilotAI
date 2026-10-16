Feature: Human governed project lifecycle
  Signed-in accountable owners progress a versioned baseline with reviewable evidence.
  Fixture results are human attestations and never represent a real deployment.

  Scenario: Complete every human lifecycle handoff and retain attributable approvals
    Given a signed-in lifecycle administrator has a requirements project
    When the human completes the lifecycle through "closed"
    Then the lifecycle is "closed" after reloading
    And four version-specific human lifecycle approvals are retained
    And the lifecycle dashboard queue matches the project state

  Scenario: Evidence is mandatory and concurrent decisions cannot overwrite progress
    Given a signed-in lifecycle administrator has a requirements project
    When the human advances without lifecycle evidence
    Then the lifecycle operation returns 409
    When the human completes the lifecycle through "ba_validation"
    And the human submits an outdated lifecycle revision
    Then the lifecycle operation returns 409
    And the lifecycle is "ba_validation" after reloading

  Scenario: Stakeholder rejection returns work to clarification and blocks advancement
    Given a signed-in lifecycle administrator has a requirements project
    When the human completes the lifecycle through "stakeholder_approval"
    And the human requests lifecycle rework
    Then the lifecycle operation returns 201
    And the lifecycle is "clarification" after reloading
    And the lifecycle dashboard queue matches the project state

  Scenario: Defects return to development and require a separate QA retest
    Given a signed-in lifecycle administrator has a requirements project
    When the human completes the lifecycle through "qa_testing"
    And the human requests lifecycle rework
    Then the lifecycle is "defect_resolution" after reloading
    When the human completes the lifecycle through "qa_retesting"
    Then the lifecycle is "qa_retesting" after reloading
    When the human completes the lifecycle through "qa_signoff"
    Then the lifecycle is "qa_signoff" after reloading

  Scenario: Changing an approved baseline flags previous evidence and resets approval work
    Given a signed-in lifecycle administrator has a requirements project
    When the human completes the lifecycle through "release_approval"
    And the human changes the lifecycle requirements baseline
    Then the lifecycle is "requirements_analysis" after reloading
    And earlier lifecycle evidence is flagged as impacted

  Scenario: Project membership does not grant a developer BA transition authority
    Given a signed-in lifecycle administrator has a requirements project
    When an invited developer attempts the current lifecycle transition
    Then the lifecycle operation returns 403
    And the lifecycle is "requirements_analysis" after reloading

  Scenario: Requirement revisions retain story and test traceability and flag change impacts
    Given a signed-in lifecycle administrator has a requirements project
    When the human links requirements stories and tests then revises the requirement
    Then the lifecycle is "requirements_analysis" after reloading

  Scenario: Extend the agent catalogue without removing testing agents or model policy
    Given a signed-in lifecycle administrator has a requirements project
    Then existing testing agents coexist with lifecycle agents and enforced provider models

  Scenario: Ready stories require the accountable upstream refinement handoffs
    Given a signed-in lifecycle administrator has a requirements project
    Then story readiness is denied before refinement and allowed after human handoffs

  Scenario: Ordered SDLC steps come from authoritative workflow and follow rejection handoffs
    Given a signed-in lifecycle administrator has a requirements project
    Then the ordered SDLC workspace follows human gates and returns to the rework step

  Scenario: Inline requirement review retains discussion and exact approved versions
    Given a signed-in lifecycle administrator has a requirements project
    Then inline requirement edits and comments persist through stakeholder approval

  Scenario: Stale review comments cannot overwrite newer requirement context
    Given a signed-in lifecycle administrator has a requirements project
    Then stale inline review comments are rejected without losing version history

  Scenario: Invited developers can discuss requirements but cannot accept BA suggestions
    Given a signed-in lifecycle administrator has a requirements project
    Then developer inline review access preserves requirement editing permissions

  Scenario: Invented agent suggestions cannot be recorded as reviewed output
    Given a signed-in lifecycle administrator has a requirements project
    Then an unknown inline AI suggestion is rejected without modifying the requirement
