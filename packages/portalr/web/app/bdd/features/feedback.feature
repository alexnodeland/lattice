Feature: Feedback
  A person gives thumbs, and says why if they like, on a rule's run and on the agent's turn.

  Background:
    Given bob has signed in
    And they open the workspace "notes"

  Scenario: Thumbs down, and why, on a rule's run
    When they publish a ticket that succeeds
    And they open the workspace's runs
    Then its run is "Succeeded"
    When they find its run not helpful, saying "Too slow"
    Then its run shows "You said: Too slow"

  Scenario: Thumbs up on the agent's turn
    When they start a thread of their own
    And they post "hello"
    And they open the workspace's runs
    Then their thread's turn is "Done"
    When they find their thread's turn helpful
    Then their thread's turn shows them finding it helpful
