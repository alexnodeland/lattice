Feature: Access
  A tenant's owners and admins see and change who may do what in it: its members, invited by
  email or made as service principals; its groups; and its service principals' keys. Each
  destructive change is confirmed first.

  Scenario: An owner invites someone, and removes them
    Given alice has signed in to admin
    When they open Access's Members
    And they invite someone new
    Then the one they invited is a member
    When they remove the one they invited
    Then the one they invited isn't a member

  Scenario: A service principal's key, shown once and revoked
    Given alice has signed in to admin
    When they open Access's Members
    And they add a service principal
    And they open Access's Keys
    And they issue it a key
    Then its key is listed, by its id alone
    When they revoke its key
    Then it has no key

  Scenario: A group, made and deleted
    Given alice has signed in to admin
    When they open Access's Groups
    And they make a group of "bob"
    Then the group is listed with "bob"
    When they delete the group
    Then the group isn't listed

  Scenario: On a phone, Access is a list of cards
    Given alice has signed in to admin
    When they look on a phone, at Access's Members
    Then the members are cards, and no table
