Feature: The admin of a generated application
  A tenant's owner opens admin on an application the template generated, and sees the people of
  their tenant by email, which the application names through Supabase Auth's admin API with its
  own secret key (portalr ADR-0040, stackr ADR-0038). stackr's smoke test runs this against the
  application it starts, with alice the owner of acme and bob a member.

  Scenario: An owner opens admin on their tenant
    Given alice has signed in to admin
    Then they're in "acme"
    And they see the page "acme"

  Scenario: The tenant's people are named by email
    Given alice has signed in to admin
    When they open Access's Members
    Then the members include "alice@portalr.test"
    And the members include "bob@portalr.test"
