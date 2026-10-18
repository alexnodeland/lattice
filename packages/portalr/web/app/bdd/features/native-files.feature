Feature: Native files
  A person reads a Word document the workspace keeps as a native file: its name, outline and
  pages, as its app reads and draws them, and downloads it, whoever holds it. They check it out,
  which opens the app's hosted editor on a site of its own, and check the file they saved back in
  (lattice RFC-0003): a check-in after the file moved on is a proposal, one sent again after an
  answer that never came makes nothing new, and the agent, asked while the file is checked out,
  is told to plan again after the check-in, which it does when asked again.

  Background:
    Given bob has signed in
    And they open the workspace "notes"
    When they start the thread "Documents"
    And they post "draft the brief"
    And they keep the document the assistant drafted

  Scenario: A drafted document's outline, pages and download
    When they open the document
    Then its outline reads:
      | Brief                   |
      | Brief starts on Monday. |
      | Who comes.              |
      | What to bring.          |
    And its first page of 2 is drawn
    And it is available to check out
    When they download it
    Then they have "brief.docx"

  Scenario: A check-out opens the editor apart, and a check-in is a revision
    When they open the document
    And they check it out
    Then the editor opened in a tab of its own, and called nothing out
    And they have "brief.docx"
    And it is checked out by them
    When they check in the brief with "Everyone comes." for "Who comes."
    Then the file says "Checked in brief.docx as version 2."
    And it is available to check out
    And its outline reads:
      | Brief                   |
      | Brief starts on Monday. |
      | Everyone comes.         |
      | What to bring.          |

  Scenario: A check-in after the file moved on is a proposal, with both versions' pages
    When they ask the assistant to revise the document
    Then the assistant says "Proposed as"
    When they open the document
    And they check it out
    And they accept the assistant's proposal there
    And they check in the brief with "Everyone comes." for "Who comes."
    Then the file says "brief.docx changed after you checked it out, so your check-in is a proposal"
    When they open the workspace's proposals
    Then the check-in is a proposal there, with its pages beside version 2's

  Scenario: A check-in whose answer never came is sent again, and makes nothing new
    When they open the document
    And they check it out
    And they check in the brief with "Everyone comes." for "Who comes.", but the answer never comes
    Then the file says "It wasn't checked in: The connection ended before the server answered. Try again."
    When they send it again
    Then the file says "brief.docx was checked in already: nothing new was made."
    And its latest version is 2

  Scenario: The agent, refused while the file is checked out, plans again after the check-in
    When they open the document
    And they check it out
    And they ask the assistant to revise the document
    Then the assistant says "is checked out by user:bob"
    And the assistant says "plan again once it is checked in"
    When they open the document
    And they check in the brief with "Everyone comes." for "Who comes."
    And they ask the assistant to revise the document
    Then the assistant says "Proposed as"
