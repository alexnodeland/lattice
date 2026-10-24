Feature: Diagrams
  A person asks the assistant to draw, and accepts the diagram it proposes; the diagram is shown
  where it was made, with its text version, and opens on its canvas, loaded then, under the
  portal's own policy, asking nothing of any other origin, and left by the keyboard (lattice
  RFC-0006, portalr ADR-0072).

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
