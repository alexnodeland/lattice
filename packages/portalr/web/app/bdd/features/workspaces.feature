Feature: Workspaces
  A person opens the workspaces grantr lets them open, in the tenant they chose.

  Scenario: Opening a workspace
    Given bob has signed in
    When they open the workspace "notes"
    Then they see the page "notes"
    When they go back to every workspace in "acme"
    Then they see the workspaces "notes" and "plans"
