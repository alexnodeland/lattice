Feature: Tenants
  A deployment's operators see every tenant, and create one with its first owner, by email, once
  confirmed. Tenants aren't entered from here, and no one else is shown the page. The deployment's
  audit log is theirs too.

  Scenario: An operator sees every tenant
    Given ops has signed in to admin
    When they open Tenants
    Then they see the tenants "acme" and "globex"

  Scenario: An operator creates a tenant with its owner by email, and can't create it twice
    Given ops has signed in to admin
    When they open Tenants
    And they fill in a new tenant, owned by "founder@portalr.test"
    And they ask to create it
    Then they are asked to confirm creating it
    When they confirm
    Then the tenant is created, owned by "founder"
    And the tenants include the new tenant
    And the owner's email is not on the page
    When they fill in the same tenant again, owned by "founder@portalr.test"
    And they ask to create it
    And they confirm
    Then they are told the tenant exists

  Scenario: Someone who administers a tenant is not shown the deployment's Tenants
    Given alice has signed in to admin
    When they open admin at "/deployment/tenants"
    Then they see the page "acme"

  Scenario: An operator reads the deployment's audit log
    Given ops has signed in to admin
    When they open the deployment's Audit
    Then they see the deployment's audit log
