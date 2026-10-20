Feature: Source grounded inline BA review
  Synthetic provider fixtures exercise the real authenticated API, persistence and approval controls.
  They do not prove live model quality or represent approved lender policies.

  Scenario Outline: Automotive finance findings retain exact source evidence and typed outcomes
    Given a signed-in BA reviewer has the synthetic BRD "<case>"
    When the reviewer analyses the saved BRD baseline
    Then the BA review contains a source-linked "<type>" finding
    And AI analysis has not signed off or changed the original BRD

    Examples:
      | case              | type                       |
      | pcp-gmfv          | CALCULATION_GAP             |
      | term-conflict     | CONFLICT                    |
      | api-validation    | INCOMPLETE_BUSINESS_RULE    |
      | pch-maintenance   | CALCULATION_GAP             |
      | duplicate         | DUPLICATE                   |
      | regulated-status  | COMPLIANCE_REVIEW_REQUIRED  |
      | rejected-proposal | AMBIGUITY                   |
      | revised-brd       | AMBIGUITY                   |
      | prompt-injection  | UNSUPPORTED_ASSUMPTION      |
      | unknown-product   | UNSUPPORTED_ASSUMPTION      |

  Scenario: BA rejection persists and is not automatically reapplied by reanalysis
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    And the BA rejects the recommendation and reanalyses unchanged material
    Then the rejected proposal and human audit history survive reloading
    And AI analysis has not signed off or changed the original BRD

  Scenario: Human signoff is version-bound and stale decisions cannot overwrite it
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    Then pending findings block BA signoff
    When the BA rejects the recommendation and signs off the reviewed baseline
    Then the human BA signoff is recorded without business approval
    And a new BRD version invalidates the previous BA review

  Scenario: Critical calculation gaps cannot be bypassed by marking a finding resolved
    Given a signed-in BA reviewer has the synthetic BRD "pcp-gmfv"
    When the reviewer analyses the saved BRD baseline
    Then resolving the calculation finding does not permit BA signoff

  Scenario: Review actions require a human BA role and project membership
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    Then an invited developer cannot decide BA findings
    And a different account cannot read the BA review

  Scenario Outline: Inline human actions persist with attributed before and after evidence
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    And the BA records the finding action "<action>"
    Then the saved finding review status is "<status>"
    And AI analysis has not signed off or changed the original BRD

    Examples:
      | action  | status                  |
      | accept  | ACCEPTED_DRAFT          |
      | edit    | EDITED_DRAFT            |
      | clarify | CLARIFICATION_REQUESTED |
      | comment | PENDING                 |
      | resolve | RESOLVED                |

  Scenario: Cancellation leaves a persistent cancelled run without approval
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer cancels a queued BRD analysis
    Then the BA analysis stays cancelled after reloading
    And no supporting requirement drafts were created

  Scenario: Completed AI analysis fills supporting drafts without human approval
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    Then the AI creates source-linked draft supporting requirements with an attributed history
    And AI analysis has not signed off or changed the original BRD

  Scenario: Reanalysis retains human edits and avoids duplicate supporting records
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    And the BA edits a supporting draft and reanalyses the BRD
    Then reanalysis preserves the human draft without creating duplicate supporting records
    And AI analysis has not signed off or changed the original BRD

  Scenario: A new BRD version retains the earlier supporting draft history
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    And the BA analyses a new version of the same BRD
    Then the earlier supporting drafts remain impacted and the new version has separate drafts

  Scenario: BA story drafting is blocked before human signoff
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    Given a BA project member is ready to draft stories
    Then the BA cannot create a story without current baseline signoff

  Scenario: Human BA signoff enables draft user stories in Backlog
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    Given a BA project member is ready to draft stories
    When the BA rejects the recommendation and signs off the reviewed baseline
    Then the BA can create linked draft stories without granting business approval

  Scenario: Revising the BRD closes the BA story drafting gate
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    Given a BA project member is ready to draft stories
    When the BA rejects the recommendation and signs off the reviewed baseline
    And the BRD is revised after BA signoff
    Then the BA cannot create a story without current baseline signoff

  Scenario: Business review documents and metrics download as versioned files
    Given a signed-in BA reviewer has the synthetic BRD "rejected-proposal"
    When the reviewer analyses the saved BRD baseline
    Given a BA project member is ready to draft stories
    When the BA rejects the recommendation and signs off the reviewed baseline
    Then the BA can download source backed business documents and metrics
    And an unrelated account cannot download the business documents
