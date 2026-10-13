Feature: Audit
  A tenant's owners and admins read grantr's log of every change to who may do what in it, the
  newest on top, filtered by the type of change and who made it.

  Scenario: A change, found in the audit log by its type
    Given alice has signed in to admin
    When they open Access's Members
    And they add a service principal
    And they open the audit log, filtered to members added
    Then the log says they added it
