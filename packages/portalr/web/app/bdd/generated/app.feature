Feature: The portal of a generated application
  A person signs in to an application the template generated, with Supabase Auth, and works in
  it: the agent answers through the gateway. stackr's smoke test runs these against the
  application it starts, with alice the owner of acme and a thread already in its workspace
  "notes" (portalr ADR-0040).

  Scenario: Signing in, a thread, and the agent's answer
    When alice signs in
    Then they see the page "acme"
    And they see the workspace "notes"
    When they open the workspace "notes"
    And they start the thread "Hello"
    And they post "Say hello."
    Then the assistant says "stackr smoke ok"

  Scenario: A wrong password is refused
    When alice signs in with the password "not-alices"
    Then they see the page "Sign in"
    And they are told "Invalid login credentials"

  Scenario: Signing out
    Given alice has signed in
    When they sign out
    Then they see the page "Sign in"
