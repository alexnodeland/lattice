Feature: Traces
  A tenant's owners and admins see what the agents did, from the traces the application sends to
  Tempo: the newest first, and each as a tree of its spans.

  Scenario: A turn's trace opens as a tree of its spans
    Given bob has had a turn fail in acme
    And alice has signed in to admin
    When they open Traces
    Then a trace is eventually listed
    When they open the newest trace
    Then they see its spans as a tree
    And what was said in them is kept out until asked for
