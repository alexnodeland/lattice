Feature: Colour-blind mode
  A person turns colour-blind mode on in the account menu, for this browser: the charts' palette and
  patterns that hold for every reader, kept across a reload, and never for anyone else.

  Scenario: Turning it on, keeping it, and turning it off
    Given alice has signed in to admin
    Then the page is not in colour-blind mode
    When they turn colour-blind mode on
    Then the page is in colour-blind mode
    When they reload the page
    Then the page is in colour-blind mode
    When they turn colour-blind mode off
    Then the page is not in colour-blind mode
