Feature: Diagrams
  A person asks the assistant to draw, and accepts the diagram it proposes; the diagram is shown
  where it was made, with its text version, and opens on its canvas, loaded then, under the
  portal's own policy, asking nothing of any other origin, and left by the keyboard; and a person
  who may edit it draws on it, and puts an image on it, each saved as their own edit (lattice
  RFC-0006, portalr ADR-0072, ADR-0074).

  Background:
    Given bob has signed in
    And they open the workspace "notes"

  Scenario: An agent's diagram, accepted, opened on its canvas and left by the keyboard
    When they start the thread "Architecture"
    And they post "draw the stack"
    And they accept the diagram the assistant proposed
    Then the diagram "Stack" is shown with 10 elements
    And its text version reads "arrow"
    When they open its canvas
    Then the canvas draws it, under the portal's policy, from the portal's origin alone
    When they press Escape
    Then the canvas is closed, and "Open canvas" has the focus

  Scenario: A person draws on a diagram's canvas and puts an image on it, saved as theirs
    When they start the thread "Architecture"
    And they post "draw the stack"
    And they accept the diagram the assistant proposed
    And they open its canvas
    And they edit it, and draw a rectangle
    Then the canvas says "Saved"
    When they paste the image "red.png" on it
    Then the canvas says "Saved"
    And the canvas offers no way to give an element a link
    And the canvas asked nothing of another origin, and its policy refused nothing
    When they close the canvas
    Then the diagram "Stack" is shown with 12 elements
    When they open its canvas
    Then the canvas draws its image, read from the portal, under the portal's policy
    When they close the canvas
    And they open the diagram's page
    Then its versions 2 and 3 are by "You"

  Scenario: A viewer looks at a diagram on its canvas, and is offered no edit
    When they start the thread "Viewed"
    And they post "draw the stack"
    And they accept the diagram the assistant proposed
    And they sign out
    And vera has signed in
    And they open the workspace "notes"
    And they open the thread "Viewed"
    And they open its canvas
    Then the canvas draws it, under the portal's policy, from the portal's origin alone
    And the canvas offers no edit
