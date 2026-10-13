Feature: Sharing
  A workspace's admin restricts a thread to the people it's shared with, and shares it, from its
  menu; a restricted thread never reaches anyone else, someone it's shared with as a viewer reads
  it and doesn't post, and someone who has it open when it's restricted is told.

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

  Scenario: A thread restricted while it's open says so
    Given bob has signed in
    And they open the workspace "notes"
    And they start a thread of their own
    When alice restricts it in a window of her own, while they have it open
    And they try to post "is this still mine?"
    Then they're told it isn't available to them any more

  Scenario: A share taken back, and the thread gone again by its address
    Given alice has signed in
    And they open the workspace "notes"
    And they start a thread of their own
    And they restrict it
    And they share it with "erin" as editor
    Then "erin" holds editor on it
    When they revoke "erin"'s editor
    Then no one holds a role on it
    When they close the dialog
    And they sign out
    And erin has signed in
    And they choose the tenant "acme"
    And they open the workspace "notes"
    Then the thread they started isn't listed
    When they open the thread they started by its address
    Then they see "Thread not found"

  Scenario: A workspace's admin shares with its people, and lifts a restriction
    Given dana has signed in
    And they open the workspace "notes"
    And they start a thread of their own
    And they restrict it
    And they open its sharing
    Then they're offered "bob", and not "alice"
    When they close the dialog
    And they lift its restriction

  Scenario: A viewer has no thread actions, and no composer
    Given bob has signed in
    And they open the workspace "notes"
    And they start a thread of their own
    When they sign out
    And vera has signed in
    And they open the workspace "notes"
    And they open the thread they started
    Then they have no thread actions
    And they can read it, and not post in it
