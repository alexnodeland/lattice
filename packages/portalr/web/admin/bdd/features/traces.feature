Feature: Traces
  A tenant's owners and admins see what the agents did, from the traces the application sends to
  Tempo: the newest first, and each as a tree of its spans. What a span says, its prompt and
  completion, stays out of the page until that span is asked for.

  Scenario: A turn that failed has a trace, which opens as a tree of its spans
    Given bob has had a turn fail in acme
    And alice has signed in to admin
    When they open Traces
    Then a trace is eventually listed
    When they open the newest trace
    Then they see its spans as a tree

  Scenario: A model call's prompt is withheld until that span is asked for
    Given a trace with a prompt has been sent for acme
    And alice has signed in to admin
    When they find that trace by its thread
    And they open the newest trace
    And they choose the span "chat claude"
    Then its prompt is not in the page, nor was it sent to it
    And it names what it withheld
    When they ask to see what the span withheld
    Then its prompt is in the page
    And no other span shows a prompt
