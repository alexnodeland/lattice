Feature: Tools
  A deployment's operators get links into Langfuse and Grafana for a trace, a session, a run or a
  tenant. Those tools aren't scoped to a tenant, so the page says that they are outside the gates
  of Traces and Logs, and that opening them is recorded. Only operators are shown the page.

  Scenario: An operator is told what the tools are outside of, and gets links for a trace and a tenant
    Given ops has signed in to admin
    When they open Tools
    Then they are told the tools are outside portalr's gates
    When they ask for the links of the trace "bdd-trace-1" and the tenant "acme"
    Then they get links into Grafana for the trace and for the tenant
    And they are told Langfuse isn't configured here
    And no link is a script and no key is on the page

  Scenario: Someone who administers a tenant is not shown the deployment's Tools
    Given alice has signed in to admin
    When they open admin at "/deployment/tools"
    Then they see the page "acme"
