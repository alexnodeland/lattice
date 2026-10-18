Feature: Tracker links
  A run that filed an item in the workspace's task tracker links to it, and so does a run that a
  change there set off. Opening one needs no record: the tracker checks who may see the item.

  Scenario: A dead-lettered run links to the item it was filed as
    Given bob has signed in
    And they open the workspace "notes"
    When they publish a ticket that fails
    And they open the workspace's runs
    Then its run is "Dead-lettered"
    And its run links to the item it was filed as, in Plane

  Scenario: A run that a change in the tracker set off links to that item
    Given bob has signed in
    And they open the workspace "notes"
    When they publish a ticket that fails
    And they open the workspace's runs
    And its run links to the item it was filed as, in Plane
    And someone renames that item in the tracker
    Then a follow-up run links to the item it came from
