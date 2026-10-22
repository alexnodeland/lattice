Feature: Integrations
  A tenant's owners and admins switch what the tenant and each of its workspaces offer beyond the
  basics, on or off, or back to what a level inherits, and the audit log records who did. A
  scenario sets back what it changed, so it can run again on the same application.

  Scenario: An integration turned off in a workspace, who did it in the audit log, and back
    Given alice has signed in to admin
    When they open Integrations for the workspace "notes"
    And they turn "Math" off
    Then "Math" is off, set here
    When they open the audit log, filtered to integrations switched
    Then the log says alice turned "markdown:math" off in workspace "notes"
    When they open Integrations for the workspace "notes"
    And they set "Math" back to inherited
    Then "Math" is on, by default
