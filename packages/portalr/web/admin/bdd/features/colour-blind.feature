Feature: Colour-blind friendly charts
  A person turns colour-blind friendly charts on in the account menu, for this browser: a palette and
  patterns that hold for every reader, kept across a reload, and never for anyone else.

  Scenario: Turning it on, keeping it, and turning it off
    Given alice has signed in to admin
    Then the charts are not colour-blind friendly
    When they turn colour-blind friendly charts on
    Then the charts are colour-blind friendly
    When they reload the page
    Then the charts are colour-blind friendly
    When they turn colour-blind friendly charts off
    Then the charts are not colour-blind friendly
