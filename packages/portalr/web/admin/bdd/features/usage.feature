Feature: Usage
  A tenant's owners and admins see what its agents spent, per day and per workspace, from
  LiteLLM. The test application runs without LiteLLM, as an application may.

  Scenario: Without LiteLLM, Usage says it isn't configured
    Given alice has signed in to admin
    When they open Usage
    Then it says LiteLLM isn't configured
