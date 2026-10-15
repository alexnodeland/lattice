Feature: Feedback
  A tenant's owners and admins see what people and evaluators said of the agent, summed by day
  from Langfuse's scores. The test application runs without Langfuse, as an application may.

  Scenario: Without Langfuse, Feedback says it isn't configured
    Given alice has signed in to admin
    When they open Feedback
    Then it says Langfuse isn't configured
