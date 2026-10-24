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
    When they change only its description, in the JSON shown, to "Triage it thrice"
    Then they see "Stored in this workspace, version 3."
    When they archive their rule
    Then their rule isn't listed
    When they open their rule's page again
    Then they see "Rule not found"

  Scenario: A rule reflexr refuses says why on its field
    Given alice has signed in
    And they open the workspace "notes"
    When they open the workspace's rules
    And they install "not json"
    Then the field says "That isn't JSON"
    When they install a rule with no throttle
    Then the field says "The rule wasn't installed: what was asked for isn't valid: rule.when.throttle."
    When they install a rule whose throttle allows "ten"
    Then the field says "rule.when.throttle.at_most"

  Scenario: An edit over someone else's is refused
    Given alice has signed in
    And they open the workspace "notes"
    When they open the workspace's rules
    And they install a rule of their own
    And they open their rule
    And the rule is changed elsewhere to "Triage it elsewhere"
    And they describe their rule as "Triage it here"
    Then the field says "The rule wasn't saved: that can't be done as things stand."
    And they see "Stored in this workspace, version 2."
    And they see "Version 2 was saved since you opened this."
    When they load version 2
    And they describe their rule as "Triage it here"
    Then they see "Stored in this workspace, version 3."
