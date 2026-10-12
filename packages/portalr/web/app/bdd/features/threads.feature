Feature: Threads
  A person chats with the workspace's agent in a thread: they see its answer as it streams,
  answer what it asks, approve what it would do, and accept or reject what it proposes.

  Background:
    Given bob has signed in
    And they open the workspace "notes"

  Scenario: Starting a thread, and the agent's answer
    When they start the thread "Hello"
    And they post "hello"
    Then the assistant says "You said: hello"

  Scenario: Answering the agent's question
    When they start the thread "Question"
    And they post "ask me something"
    Then the agent asks "Which week?"
    When they answer "The next"
    Then the assistant says "Done: The next"

  Scenario: Approving what the agent would do
    When they start the thread "Approval"
    And they post "publish the notes"
    Then the agent asks to run "publish"
    When they approve it
    Then the assistant says "Done: Published the notes"

  Scenario: Accepting a proposal
    When they start the thread "Accepting"
    And they post "propose an edit"
    Then they see the proposal "Move the launch to Tuesday"
    When they accept it
    Then the proposal is "Accepted"
    And the note says "Launch on Tuesday."

  Scenario: Rejecting a proposal
    When they start the thread "Rejecting"
    And they post "propose an edit"
    Then they see the proposal "Move the launch to Tuesday"
    When they reject it
    Then the proposal is "Rejected"
    And the note says "Launch on Monday."

  Scenario: Thumbs on the agent's answer
    When they start the thread "Thumbs"
    And they post "hello"
    And they find the assistant's answer helpful
    Then the answer shows them finding it helpful
