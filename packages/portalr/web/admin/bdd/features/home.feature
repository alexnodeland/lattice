Feature: Home
  admin opens for a tenant's owners and admins on their tenant, and for the deployment's
  operators on every tenant; each of Home's cards reads on its own, and says so when its tool
  isn't there.

  Scenario: A tenant's owner opens admin on their tenant
    Given alice has signed in to admin
    Then they're in "acme"
    And they see the page "acme"
    And the areas are "Home, Access"
    And the "Members" card shows a figure
    And the "Workspaces" card shows a figure
    And the "Failed turns" card shows a figure
    And the "Feedback" card says "Langfuse isn't configured."
    And the "Spend" card says "LiteLLM isn't configured."

  Scenario: An operator opens admin on every tenant
    Given ops has signed in to admin
    Then they're in "All tenants"
    And they see the page "All tenants"
    And the areas are "Home"
    And the "Tenants" card shows a figure
    And the "Spend" card says "LiteLLM isn't configured."

  Scenario: An editor has no admin
    Given bob has signed in to admin
    Then they see the page "No access"

  Scenario: A tenant someone doesn't administer isn't theirs to open
    Given dana has signed in to admin
    When they open admin at "/t/acme"
    Then they see the page "Not a tenant you administer"
