Feature: Runs
  A tenant's owners and admins see a workspace's rule runs live, those that need someone first,
  and may retry, skip or cancel a run, each after a confirmation. What people did to a run stays
  with it. The scenarios use the test application's triage rule, which fails a ticket whose
  subject starts with "fail".

  Scenario: A dead-lettered run is retried only once it is confirmed, and says who retried it
    Given bob has published a ticket that fails in acme
    And alice has signed in to admin
    When they open Runs
    Then the run is "Dead-lettered"
    When they ask to retry the run but think better of it
    Then the run is "Dead-lettered"
    And the run has no history
    When they retry the run, confirming
    Then the run shows a history of 1

  Scenario: A dead-lettered run is skipped with a reason, which stays with it
    Given bob has published a ticket that fails in acme
    And alice has signed in to admin
    When they open Runs
    And they skip the run, saying "a known outage"
    Then the run is no longer among those that need someone
    When they show every state
    Then the run is "Skipped"
    And the run's history says "a known outage"

  Scenario: A dead-lettered run is cancelled
    Given bob has published a ticket that fails in acme
    And alice has signed in to admin
    When they open Runs
    And they cancel the run, saying "not needed"
    And they show every state
    Then the run is "Cancelled"
    And the run's history says "not needed"

  Scenario: What a dead letter is, is said
    Given alice has signed in to admin
    When they open Runs
    Then they are told that a dead-lettered run failed every attempt
