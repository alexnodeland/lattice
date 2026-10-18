Feature: Native files
  A person reads a Word document the workspace keeps as a native file: its name, outline and
  pages, as its app reads and draws them, and downloads it, whoever holds it.

  Background:
    Given bob has signed in
    And they open the workspace "notes"

  Scenario: A drafted document's outline, pages and download
    When they start the thread "Drafts"
    And they post "draft the brief"
    And they keep the document the assistant drafted
    And they open the document
    Then its outline reads:
      | Brief                   |
      | Brief starts on Monday. |
      | Who comes.              |
      | What to bring.          |
    And its first page of 2 is drawn
    And it is available to check out
    When they download it
    Then they have "brief.docx"
