Feature: Logs
  A tenant's owners and admins see what the application wrote, from the logs it sends to Loki, and
  how it is doing, from Prometheus. A record is listed with its time, level, service, thread and
  run, and the length of its line: the line itself, which may hold what a person or a model said,
  stays out of the page until that record is asked for.

  Scenario: A log line is withheld until its record is asked for
    Given a log record with a phrase has been sent for acme
    And alice has signed in to admin
    When they open Logs
    And they find that record by its thread
    Then its phrase is not in the page, nor was it sent to it
    And it names the length of its line
    When they ask to see its line
    Then its phrase is in the page
    And the phrase came in a read for that record alone

  Scenario: Health shows its charts with the step of each point
    Given alice has signed in to admin
    When they open Logs
    Then they see the health charts, or why there are none
    And each point is said to be a minute
