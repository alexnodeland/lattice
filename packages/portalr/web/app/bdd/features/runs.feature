Feature: Runs
  A person sees the workspace's runs, the agent's turns and its rules' runs, and acts on each as
  its library and grantr allow.

  Scenario: A rule's failing run is dead-lettered, then skipped
    Given bob has signed in
    And they open the workspace "notes"
    When they publish a ticket that fails
    And they open the workspace's runs
    Then its run is "Dead-lettered"
    When they skip its run
    Then its run is "Skipped"

  Scenario: A dead-lettered run is retried, and fails again
    Given bob has signed in
    And they open the workspace "notes"
    When they publish a ticket that fails
    And they open the workspace's runs
    Then its run is "Dead-lettered"
    When they retry its run
    Then its run shows "retried once"
    And its run is "Dead-lettered"
    And its run shows "attempt 2"

  Scenario: A running turn is stopped
    Given bob has signed in
    And they open the workspace "notes"
    When they start a thread of their own
    And they post "wait a while"
    And they open the workspace's runs
    Then their thread's turn is "Working"
    When they stop their thread's turn
    Then their thread's turn is "Stopped"

  Scenario: A paused turn can't be stopped: its questions are answered in its thread
    Given bob has signed in
    And they open the workspace "notes"
    When they start a thread of their own
    And they post "ask me something"
    And they open the workspace's runs
    Then their thread's turn is "Waiting for someone"
    And their thread's turn has no Stop

  Scenario: A viewer sees runs, and can't retry or skip them
    Given bob has published a ticket that fails
    And vera has signed in
    And they open the workspace "notes"
    And they open the workspace's runs
    Then they can't retry or skip its run
    And the server refuses their own retry of it
