Feature: Artifacts
  A person reads the workspace's artifacts, each through its kind's renderer, and sees what each
  revision changed.

  Background:
    Given bob has signed in
    And they open the workspace "notes"

  Scenario: An accepted proposal's change, in the note and its revisions
    When they start the thread "Revisions"
    And they post "propose an edit"
    And they keep the note the assistant proposed an edit to
    And they accept it
    And they open the workspace's artifacts
    And they open the note
    Then the note reads "Launch on Tuesday."
    And its latest revision removed "Monday" and added "Tuesday"

  Scenario: Accepting a proposal on the note's own page
    When they start the thread "On the note"
    And they post "propose an edit"
    And they keep the note the assistant proposed an edit to
    And they open the workspace's artifacts
    And they open the note
    Then the note reads "Launch on Monday."
    When they accept it
    Then the note reads "Launch on Tuesday."
