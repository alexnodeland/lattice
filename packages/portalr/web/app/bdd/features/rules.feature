Feature: Rules
  A person sees the workspace's rules and the schedules that tick into it, and a workspace's admin
  installs, edits and archives stored rules as reflexr's JSON.

  Scenario: An editor sees the rules and schedules, and changes none
    Given bob has signed in
    And they open the workspace "notes"
    When they open the workspace's rules
    Then the rule "portalr:triage" is listed "in code"
    And the schedule "portalr:digest" is listed
    And they can't install a rule
    When they open the rule "portalr:triage"
    Then they see "In the application's code, the same in every workspace."
    And they can't edit or archive it

  Scenario: An admin installs a stored rule, edits it, and archives it
    Given alice has signed in
    And they open the workspace "notes"
    When they open the workspace's rules
    And they install a rule of their own
    Then their rule is listed "stored, version 1"
    When they open their rule
    And they describe their rule as "Triage it twice"
    Then they see "Stored in this workspace, version 2."
    When they archive their rule
    Then their rule isn't listed

  Scenario: A rule reflexr refuses says why on its field
    Given alice has signed in
    And they open the workspace "notes"
    When they open the workspace's rules
    And they install "not json"
    Then the field says "That isn't JSON"
    When they install a rule with no throttle
    Then the field says "when.throttle is required"

  Scenario: An edit over someone else's is refused
    Given alice has signed in
    And they open the workspace "notes"
    When they open the workspace's rules
    And they install a rule of their own
    And they open their rule
    And someone else has described their rule as "Triage it elsewhere"
    And they describe their rule as "Triage it here"
    Then the field says "is at version 2, not 1"
