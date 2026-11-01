Feature: Approvals
  A person answers, in one place, the calls in any of the tenant's workspaces that wait for their
  yes; their own admin action is confirmed on admin's confirm page alone.

  Background:
    Given alice has signed in
    And they open the tenant's approvals

  Scenario: Approving an agent's call on its page
    Then "Publish the weekly note" waits for them, asked by the agent notes for bob
    When they approve "Publish the weekly note" because "Looks right."
    Then it is approved by alice, because "Looks right."

  Scenario: Confirming their own admin action in admin
    Then "Revoke the key ci" is theirs to confirm in admin
    When they confirm "Revoke the key ci" in admin, typing "acme"
    Then it is approved by alice on the confirm page
