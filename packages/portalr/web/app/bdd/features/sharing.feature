Feature: Sharing
  A workspace's admin restricts a thread to the people it's shared with, and shares it, from its
  menu; a restricted thread never reaches anyone else, and someone it's shared with as a viewer
  reads it and doesn't post.

  Scenario: A restricted thread is hidden, then shared as a viewer
    Given bob has signed in
    And they open the workspace "notes"
    And they start a thread of their own
    And they have no thread actions
    When they sign out
    And alice has signed in
    And they open the workspace "notes"
    And they open the thread they started
    And they restrict it
    And they sign out
    And bob has signed in
    And they open the workspace "notes"
    Then the thread they started isn't listed
    When they sign out
    And alice has signed in
    And they open the workspace "notes"
    And they open the thread they started
    And they share it with "bob" as viewer
    Then "bob" holds viewer on it
    When they close the dialog
    And they sign out
    And bob has signed in
    And they open the workspace "notes"
    And they open the thread they started
    Then they can read it, and not post in it

  Scenario: A share taken back, and a restriction lifted
    Given alice has signed in
    And they open the workspace "notes"
    And they start a thread of their own
    And they restrict it
    And they share it with "erin" as editor
    Then "erin" holds editor on it
    When they revoke it
    Then no one holds a role on it
    When they close the dialog
    And they lift its restriction
