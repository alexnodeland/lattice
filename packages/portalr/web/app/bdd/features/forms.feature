Feature: Forms the agent asks
  The agent asks a form through ask_form (lattice RFC-0005), which pauses its turn: a person fills
  it in, is told under a field what it won't take, sends it, and the turn resumes with the values.

  Background:
    Given bob has signed in
    And they open the workspace "notes"

  Scenario: A form refused for a field, then answered, and the turn resumes
    When they start the thread "Leave"
    And they post "form a few days off"
    Then the agent asks the form "Request leave"
    When they fill in "Working days" with "40"
    And they send it with "Ask for leave"
    Then "Working days" is refused with "Enter 30 or less."
    When they fill in "Working days" with "3"
    And they send it with "Ask for leave"
    Then the assistant says "Done: 3 working days off"
