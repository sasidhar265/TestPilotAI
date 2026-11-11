Feature: Knowledge agent lifecycle
  Administrators can review and publish knowledge contributors without source edits.
  Drafts never affect the live workflow and previous publications remain available.

  Scenario: A new knowledge draft is excluded from the live catalog
    When I create knowledge contributor "reference-contributor"
    Then the knowledge response status is 201
    And the active knowledge revision is 0
    And the knowledge contributor is excluded from the live agent catalog

  Scenario: Publishing an unreviewed draft is rejected
    When I create knowledge contributor "reference-contributor"
    And I "publish" knowledge revision 1
    Then the knowledge response status is 409
    And the active knowledge revision is 0

  Scenario: A reviewed knowledge agent can be published
    When I create knowledge contributor "reference-contributor"
    And I review knowledge revision 1
    Then the knowledge response status is 200
    When I "publish" knowledge revision 1
    Then the knowledge response status is 200
    And the active knowledge revision is 1
    And the knowledge contributor is included in the live agent catalog

  Scenario: Draft editing keeps the previous publication active
    When I create knowledge contributor "reference-contributor"
    And I review knowledge revision 1
    And I "publish" knowledge revision 1
    And I update knowledge contributor from "changed-reference" expecting revision 1
    Then the knowledge response status is 200
    And the active knowledge revision is 1

  Scenario: A previous published revision can be activated again
    When I create knowledge contributor "reference-contributor"
    And I review knowledge revision 1
    And I "publish" knowledge revision 1
    And I update knowledge contributor from "changed-reference" expecting revision 1
    And I review knowledge revision 2
    And I "publish" knowledge revision 2
    Then the active knowledge revision is 2
    When I "rollback" knowledge revision 1
    Then the knowledge response status is 200
    And the active knowledge revision is 1

  Scenario: Withdrawal removes the knowledge agent from the live catalog
    When I create knowledge contributor "reference-contributor"
    And I review knowledge revision 1
    And I "publish" knowledge revision 1
    And I "withdraw" knowledge revision 1
    Then the knowledge response status is 200
    And the active knowledge revision is 0
    And the knowledge contributor is excluded from the live agent catalog

  Scenario: Concurrent draft edits are rejected
    When I create knowledge contributor "reference-contributor"
    And I update knowledge contributor from "changed-reference" expecting revision 1
    And I update knowledge contributor from "reference-contributor" expecting revision 1
    Then the knowledge response status is 409

  Scenario: Review requires explicit approval of reference use
    When I create knowledge contributor "reference-contributor"
    And I review knowledge revision 1 without source approval
    Then the knowledge response status is 422
    And the active knowledge revision is 0

  Scenario: Anonymous changes are rejected
    When I create a knowledge contributor without authentication
    Then the knowledge response status is 401

  Scenario: A knowledge definition cannot override the enforced model
    When I create a knowledge contributor with an unapproved model field
    Then the knowledge response status is 422

  Scenario: Importing an export never transfers its publication identity
    When I create knowledge contributor "reference-contributor"
    And I review knowledge revision 1
    And I "publish" knowledge revision 1
    And I validate the exported knowledge contributor for import
    Then the knowledge response status is 200
    And the import result is a new draft definition without publication identity
    And the active knowledge revision is 1

  Scenario: Import rejects fields that override the enforced model
    When I validate a knowledge import with an unapproved model field
    Then the knowledge response status is 422

  Scenario: Import rejects unknown schema versions
    When I validate an unsupported knowledge import format
    Then the knowledge response status is 422
