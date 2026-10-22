"""What the agent reads of a diagram: its live shapes, labels and arrows, never its JSON."""

from artifactr.excalidraw import describe
from artifactr.excalidraw.render import MAX_DESCRIPTION
from tests.excalidraw.scenes import diagram, element


def test_shapes_labels_arrows_text_and_bounds() -> None:
    plan = diagram(
        element("frame1", type="frame", name="Backend", x=0, y=0, width=400, height=300),
        element("api", x=10, y=10, width=100, height=50),
        element("t1", type="text", text="API", containerId="api"),
        element("db", type="ellipse", x=200, y=10, width=100, height=50),
        element("t2", type="text", text="DB", containerId="db"),
        element(
            "a1",
            type="arrow",
            startBinding={"elementId": "api"},
            endBinding={"elementId": "db"},
        ),
        element("t3", type="text", text="reads", containerId="a1"),
        element("note", type="text", text="Draft:\n  not final", x=10, y=200),
        element("gone", isDeleted=True),
    )
    assert plan.render_for_agent() == "\n".join(
        [
            'Diagram "Plan": 8 elements',
            "Bounds: x 0 to 400, y 0 to 300",
            "Frames (1):",
            '- frame1 "Backend"',
            "Shapes (2):",
            '- rectangle api "API"',
            '- ellipse db "DB"',
            "Arrows (1):",
            '- arrow a1: api "API" --"reads"--> db "DB"',
            "Text (1):",
            '- "Draft: not final"',
        ]
    )


def test_a_free_arrow_and_an_empty_diagram() -> None:
    assert describe("Empty", {}) == 'Diagram "Empty": 0 elements'
    free = diagram(element("a1", type="line", x=None))
    assert free.render_for_agent() == "\n".join(
        ['Diagram "Plan": 1 elements', "Arrows (1):", "- line a1: (free) --> (free)"]
    ), "an element with no place adds nothing to the bounds"


def test_a_long_description_is_cut() -> None:
    many = diagram(*(element(f"e{i}") for i in range(1000)))
    said = many.render_for_agent()
    assert len(said) <= MAX_DESCRIPTION
    assert said.endswith("(cut: read the diagram for the rest)")
