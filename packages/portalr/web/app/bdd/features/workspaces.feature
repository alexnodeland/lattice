Feature: Workspaces
  A person opens the workspaces grantr lets them open, in the tenant they chose.

  Scenario: Opening a workspace
    Given bob has signed in
    When they open the workspace "notes"
    Then they are in the workspace "notes"
    When they go back to every workspace in "acme"
    Then they see the workspaces "notes" and "plans"
    And each links to its areas

  Scenario: A workspace's card opens one of its areas
    Given bob has signed in
    And they open the workspace "notes"
    When they go back to every workspace in "acme"
    And they open the "Runs" of the workspace "plans"
    Then they see the page "Runs"
