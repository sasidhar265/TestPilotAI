Feature: Workspace presentation contracts
  Navigation, appearance controls and the core catalog stay consistent with the current workspace.

  Scenario Outline: Current presentation contract for <page>
    Then the "<page>" page follows the current workspace presentation contract

    Examples:
      | page |
      | login |
      | home |
      | logs |
      | documentation |
      | settings |

  Scenario: Core workflow catalog order remains stable
    Then the live agent catalog preserves the approved core workflow order
