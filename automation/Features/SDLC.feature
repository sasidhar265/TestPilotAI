Feature: Agent driven SDLC
  Projects retain agent delivery evidence and immutable lifecycle versions.
  Invalid missions fail before provider calls or deployment commands.

  Scenario: Discover seven SDLC stage agents with enforced provider models
    When I request the SDLC agent catalogue
    Then the response status is 200
    And all seven SDLC stage agents and mandatory models are discoverable

  Scenario: Preserve version history without transferring approval to a revision
    Given a new SDLC delivery project exists
    When I save the "planning" SDLC Requirements fixture
    Then the response status is 201
    When I approve the first SDLC Requirements version
    Then the response status is 201
    When I save the "planning-revision" SDLC Requirements fixture
    Then the response status is 201
    When I request the SDLC project history
    Then the response status is 200
    And SDLC history preserves both versions and approval belongs only to version one

  Scenario: Reject a stale Requirements write
    Given a new SDLC delivery project exists
    When I save the "planning" SDLC Requirements fixture
    Then the response status is 201
    When I save the "planning" SDLC Requirements fixture
    Then the response status is 409

  Scenario Outline: Reject invalid delivery missions before running agents
    Given a new SDLC delivery project exists
    When I submit the "<fixture>" SDLC mission
    Then the response status is 422

    Examples:
      | fixture          |
      | short-brief      |
      | invalid-target   |
      | invalid-provider |

  Scenario: Unknown agent delivery runs return a clear not found response
    When I request an unknown SDLC delivery run
    Then the response status is 404

  Scenario Outline: Unknown run operations do not start workers or execute commands
    When I "<operation>" an unknown SDLC delivery run
    Then the response status is 404

    Examples:
      | operation |
      | cancel    |
      | resume    |

  Scenario: Requirements must exist before agents can start
    Given a new SDLC delivery project exists
    When I submit the "missing-source" SDLC mission
    Then the response status is 409

  Scenario: Reject a run against an outdated Requirements baseline
    Given a new SDLC delivery project exists
    When I save the "planning" SDLC Requirements fixture
    Then the response status is 201
    When I save the "planning-revision" SDLC Requirements fixture
    Then the response status is 201
    When I submit the "stale-source" SDLC mission
    Then the response status is 409

  Scenario: Downstream stages cannot introduce independent scope
    Given a new SDLC delivery project exists
    When I manually write a downstream SDLC output
    Then the response status is 409
