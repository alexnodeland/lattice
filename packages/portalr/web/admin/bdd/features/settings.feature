Feature: Settings
  A tenant's owners and admins lower a connected app's hourly limit for the tenant, never above
  the operator's, or the default, and set it back. A scenario sets
  back what it changed, so it can run again on the same application.

  Scenario: A tenant's limit lowered, a raise refused naming its ceiling, and back
    Given alice has signed in to admin
    When they open Settings for the tenant
    And they lower "FreeCAD's tries an hour" to 12
    Then 12 applies to "FreeCAD's tries an hour", set here
    When they try to raise "FreeCAD's tries an hour" to 1000
    Then they are told it may be at most 30, the default's value
    When they set "FreeCAD's tries an hour" back to the default
    Then 30 applies to "FreeCAD's tries an hour"
