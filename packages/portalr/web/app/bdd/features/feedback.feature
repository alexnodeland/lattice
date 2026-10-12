Feature: Feedback
  A person gives thumbs, and says why if they like, on a rule's run, the agent's turn and an
  artifact.

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

  Scenario: Thumbs up on a note
    When they start the thread "A note to judge"
    And they post "propose an edit"
    And they keep the note the assistant proposed an edit to
    And they open the workspace's artifacts
    And they open the note
    And they find the note helpful
    Then the note shows them finding it helpful

