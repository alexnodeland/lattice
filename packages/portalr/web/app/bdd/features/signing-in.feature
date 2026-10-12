Feature: Signing in
  A person signs in with Supabase Auth, and lands in the tenant they work in: grantr says which.

  Scenario: A person in one tenant goes straight to its workspaces
    When alice signs in
    Then they see the page "acme"
    And they see the workspaces "notes" and "plans"

  Scenario: A person in two tenants picks one
    When erin signs in
    Then they see the page "Choose a tenant"
    When they choose the tenant "globex"
    Then they see the page "globex"
    And they see "There is no workspace here you can open."

  Scenario: A person in no tenant learns they have no access
    When frank signs in
    Then they see the page "No access"

  Scenario: A wrong password is refused
    When alice signs in with the password "not-alices"
    Then they see the page "Sign in"
    And they are told "Invalid login credentials"

  Scenario: Signing out
    Given alice has signed in
    When they sign out
    Then they see the page "Sign in"
