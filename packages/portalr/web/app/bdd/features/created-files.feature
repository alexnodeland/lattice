Feature: Files the agent creates
  Asked for a travel plan as a Word document and a presentation, the agent creates both, blank,
  and proposes what goes in each (lattice#874). Each file's card in the thread says it was created
  empty and that the agent's changes wait for review, and each proposal says what it does, change
  by change (lattice#1090); once a change is accepted, its file's card is a file's again, read a
  page at a time.

  Background:
    Given bob has signed in
    And they open the workspace "notes"
    When they start the thread "Trip"
    And they post "write up a travel plan as a docx and pptx"
    Then the assistant says "Created the travel plan as a document and slides"

  Scenario: Two files created empty, each a file once its changes are accepted
    Then "Travel plan.docx" was created empty, its changes waiting for review
    And "Travel plan.pptx" was created empty, its changes waiting for review
    And the proposal "Write the travel plan" waits for review
    And the proposal "Write the travel plan's slides" waits for review
    And the proposal "Write the travel plan" says "Runs 3 commands: add_paragraph ×3.", change by change
    When they accept the proposal "Write the travel plan"
    Then "Travel plan.docx" is a file to read
    And "Travel plan.pptx" was created empty, its changes waiting for review
    When they accept the proposal "Write the travel plan's slides"
    Then "Travel plan.pptx" is a file to read
