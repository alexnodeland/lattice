Feature: Proposals
  A person sees every proposal in the workspace, the open ones first, and accepts or rejects one
  there, wherever it was made.

  Background:
    Given bob has signed in
    And they open the workspace "notes"

  Scenario: Rejecting a proposal from the workspace's proposals
    When they start the thread "Elsewhere"
    And they post "propose an edit"
    And they keep the note the assistant proposed an edit to
    And they open the workspace's proposals
    Then the note's proposal is open there
    When they reject the note's proposal there
    Then the note's proposal is "Rejected" there
