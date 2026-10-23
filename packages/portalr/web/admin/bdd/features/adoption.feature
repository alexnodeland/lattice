Feature: Adoption
  A tenant's owners and admins see how its people use the product, from product analytics
  that people chose to share. The test application runs without product analytics, as an
  application may.

  Scenario: Without product analytics, Adoption says it isn't configured
    Given alice has signed in to admin
    When they open Adoption
    Then it says product analytics aren't configured
