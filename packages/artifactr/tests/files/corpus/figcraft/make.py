"""FigCraft's corpus: one generated `.figcraft` per feature, beside this, each holding that feature.

Every file is written by hand, as the smallest document FigCraft reads that holds its feature, in
a zip with a fixed time on every entry, so the same code makes the same bytes. A test fails if
the committed files drift from what this makes; `python -m tests.files.corpus.figcraft.make`,
from `packages/artifactr`, writes them again.
"""

import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

HERE: Final = Path(__file__).parent
TIME: Final = (1980, 1, 1, 0, 0, 0)

Node = dict[str, Any]


def rgb(red: float, green: float, blue: float) -> list[dict[str, Any]]:
    """One solid paint of a colour."""
    color = {"r": red, "g": green, "b": blue, "a": 1.0}
    return [{"type": "solid", "color": color, "opacity": 1.0, "visible": True, "blend": "normal"}]


def node(id: int, kind: str, name: str, parent: int, **fields: Any) -> Node:
    """A layer: its id, type, name and parent, and what else it holds."""
    return {"id": id, "name": name, "type": kind, "parent": parent, **fields}


def at(x: float, y: float, width: float, height: float) -> dict[str, Any]:
    """Where a layer stands in its parent, and its size."""
    return {"transform": [1.0, 0.0, 0.0, 1.0, x, y], "width": width, "height": height}


def figcraft(*pages: tuple[str, list[Node]], **document: Any) -> bytes:
    """A `.figcraft` of its pages, each a name and its layers, whose parent `0` is the page."""
    nodes: dict[str, Node] = {}
    ids: list[int] = []
    next_id = 1 + len(pages) + sum(len(layers) for _, layers in pages)
    for index, (name, layers) in enumerate(pages):
        page = 1 + index * 100
        ids.append(page)
        own = [{**layer, "parent": layer["parent"] or page} for layer in layers]
        children = [layer["id"] for layer in own if layer["parent"] == page]
        nodes[str(page)] = {"id": page, "name": name, "type": "page", "children": children}
        nodes[str(page)].update(width=0.0, height=0.0)
        for layer in own:
            held = [other["id"] for other in own if other["parent"] == layer["id"]]
            nodes[str(layer["id"])] = {**layer, **({"children": held} if held else {})}
            next_id = max(next_id, layer["id"] + 1)
    content = {
        "format": "figcraft",
        "version": 1,
        "name": "Corpus",
        "pages": ids,
        "nodes": nodes,
        "next_id": max(next_id, ids[-1] + 1),
        **document,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo("document.json", TIME)
        archive.writestr(info, json.dumps(content), zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def frames() -> bytes:
    return figcraft(
        (
            "Page 1",
            [
                node(2, "frame", "Card", 0, **at(0, 0, 200, 100), fills=rgb(1, 1, 1)),
                node(3, "rectangle", "Inside", 2, **at(10, 10, 50, 40)),
            ],
        )
    )


def shapes() -> bytes:
    return figcraft(
        (
            "Page 1",
            [
                node(2, "rectangle", "Box", 0, **at(0, 0, 50, 40)),
                node(3, "ellipse", "Dot", 0, **at(60, 0, 30, 30)),
                node(4, "star", "Star", 0, **at(100, 0, 20, 20), count=5, inner_ratio=0.38),
            ],
        )
    )


def text() -> bytes:
    style = {"font_family": "Inter", "font_style": "Regular", "font_size": 18.0}
    return figcraft(
        (
            "Page 1",
            [
                node(2, "text", "Title", 0, **at(0, 0, 80, 22), characters="Hello", style=style),
                node(
                    3,
                    "text",
                    "Body",
                    0,
                    **at(0, 30, 120, 15),
                    characters="Second line",
                    style={**style, "font_size": 12.0},
                ),
            ],
        )
    )


def fills_and_strokes() -> bytes:
    stroke = {"weight": 2.0, "align": "inside"}
    return figcraft(
        (
            "Page 1",
            [
                node(2, "rectangle", "Red", 0, **at(0, 0, 10, 10), fills=rgb(1, 0, 0)),
                node(
                    3,
                    "rectangle",
                    "Outlined",
                    0,
                    **at(20, 0, 10, 10),
                    fills=[],
                    strokes=rgb(0, 0, 1),
                    stroke=stroke,
                ),
            ],
        )
    )


def groups() -> bytes:
    return figcraft(
        (
            "Page 1",
            [
                node(2, "group", "Pair", 0, width=30.0, height=10.0),
                node(3, "rectangle", "Left", 2, **at(0, 0, 10, 10)),
                node(4, "rectangle", "Right", 2, **at(20, 0, 10, 10)),
            ],
        )
    )


def pages() -> bytes:
    return figcraft(
        ("Cover", [node(2, "rectangle", "On the cover", 0, **at(0, 0, 10, 10))]),
        ("Details", [node(102, "rectangle", "On the details", 0, **at(0, 0, 10, 10))]),
    )


def components() -> bytes:
    return figcraft(
        (
            "Page 1",
            [
                node(2, "component", "Button", 0, **at(0, 0, 40, 20), props={}),
                node(3, "rectangle", "Fill", 2, **at(0, 0, 40, 20)),
                node(4, "instance", "Button", 0, **at(100, 0, 40, 20), component=2, props={}),
                node(5, "rectangle", "Fill", 4, **at(0, 0, 40, 20), source=3),
            ],
        )
    )


def auto_layout() -> bytes:
    layout = {"mode": "vertical", "gap": 12.0, "padding": [8.0, 8.0, 8.0, 8.0]}
    return figcraft(
        (
            "Page 1",
            [
                node(2, "frame", "Stack", 0, **at(0, 0, 66, 80), layout=layout),
                node(3, "rectangle", "First", 2, **at(8, 8, 50, 20)),
                node(4, "rectangle", "Second", 2, **at(8, 40, 50, 20)),
            ],
        )
    )


def comments() -> bytes:
    comment = {
        "id": 1, "page": 1, "x": 5.0, "y": 5.0, "anchor": None, "author": "Ada",
        "text": "Check the spacing", "created": 1790000000, "resolved": False,
        "replies": [], "read_by": ["Ada"],
    }  # fmt: skip
    return figcraft(
        ("Page 1", [node(2, "rectangle", "Box", 0, **at(0, 0, 10, 10))]), comments=[comment]
    )


def variables() -> bytes:
    collection = "VariableCollectionId:1"
    mode = f"{collection}/mode1"
    held = {
        "collections": [
            {"id": collection, "name": "Tokens", "modes": [{"id": mode, "name": "Base"}]}
        ],
        "variables": [
            {
                "id": "VariableID:1", "name": "gap", "collection": collection,
                "resolvedType": "number", "values": {mode: {"type": "number", "value": 8.0}},
                "description": "",
            }
        ],
    }  # fmt: skip
    return figcraft(
        ("Page 1", [node(2, "rectangle", "Box", 0, **at(0, 0, 10, 10))]), variables=held
    )


def styles() -> bytes:
    style = {
        "id": "S:1",
        "name": "Brand/Red",
        "description": "",
        "type": "paint",
        "paints": rgb(1, 0, 0),
    }
    refs = {"fill": "S:1", "stroke": None, "effect": None, "grid": None, "text": None}
    return figcraft(
        (
            "Page 1",
            [node(2, "rectangle", "Box", 0, **at(0, 0, 10, 10), fills=rgb(1, 0, 0), styles=refs)],
        ),
        styles=[style],
    )


FEATURES: Final[dict[str, Callable[[], bytes]]] = {
    "frames": frames,
    "shapes": shapes,
    "text": text,
    "fills_and_strokes": fills_and_strokes,
    "groups": groups,
    "pages": pages,
    "components": components,
    "auto_layout": auto_layout,
    "comments": comments,
    "variables": variables,
    "styles": styles,
}
"""Each feature FigCraft's report compares, and what makes its file."""


def main() -> None:
    for feature, make in FEATURES.items():
        (HERE / f"{feature}.figcraft").write_bytes(make())


if __name__ == "__main__":
    main()
