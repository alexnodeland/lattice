Feature: Threads
  A person chats with the workspace's agent in a thread: they see its answer as it streams,
  answer what it asks, approve what it would do, accept or reject what it proposes, and see why
  a turn failed, and try it again.

  Background:
    Given bob has signed in
    And they open the workspace "notes"

  Scenario: Starting a thread, and the agent's answer
    When they start the thread "Hello"
    And they post "hello"
    Then the assistant says "You said: hello"

  Scenario: Answering the agent's questions by choosing
    When they start the thread "Question"
    And they post "ask me something"
    Then the agent asks "Which week?"
    When they choose "The next"
    And they choose "Agenda"
    And they choose "Actions"
    And they answer
    Then the assistant says "Done: The next; Agenda, Actions"
    And the agent's questions say "The next" was chosen

  Scenario: Answering a question in their own words
    When they start the thread "Own words"
    And they post "ask me something"
    And they choose "Other"
    And they write "After the launch"
    And they choose "Decisions"
    And they answer
    Then the assistant says "Done: After the launch; Decisions"

  Scenario: A turn that fails says so, and is tried again
    When they start the thread "Failing"
    And they post "fail"
    Then the thread says 1 turn failed
    When they try it again
    Then the thread says 2 turns failed

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
