"""Each feature of a `.figcraft`, read out of its document into a value two saves compare by.

A value keeps what the feature means and leaves out what a save may rewrite without changing
it: layer ids, which are numbered again, the defaults a save writes out, such as a paint's blend,
and the thumbnail. The fidelity report opens and saves each corpus file in FigCraft and compares
its feature's value before and after (lattice RFC-0003, phase 2).
"""

import io
import json
import zipfile
from collections.abc import Callable, Iterator
from typing import Any, Final

Value = list[tuple[object, ...]]
Node = dict[str, Any]

PLACES: Final = 3
"""The decimals a number is compared to: a save writes floats its own way."""


class Design:
    """A `.figcraft`'s document: its pages, and each page's layers in order, depth first."""

    def __init__(self, content: bytes) -> None:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.document: dict[str, Any] = json.loads(archive.read("document.json"))
        self.nodes: dict[str, Node] = self.document["nodes"]

    def node(self, id: object) -> Node:
        return self.nodes[str(id)]

    def pages(self) -> list[Node]:
        return [self.node(page) for page in self.document["pages"]]

    def layers(self, under: Node | None = None) -> Iterator[Node]:
        for parent in self.pages() if under is None else [under]:
            for child in parent.get("children", []):
                yield self.node(child)
                yield from self.layers(self.node(child))


def number(value: float) -> float:
    return round(float(value), PLACES)


def box(layer: Node) -> tuple[float, ...]:
    """A layer's place in its parent and its size."""
    transform = layer.get("transform", [1, 0, 0, 1, 0, 0])
    return tuple(number(v) for v in (transform[4], transform[5], layer["width"], layer["height"]))


def colours(paints: list[Node] | None) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(number(paint["color"][c]) for c in "rgba")
        for paint in paints or []
        if paint.get("visible", True)
    )


def children(design: Design, layer: Node) -> tuple[str, ...]:
    return tuple(design.node(child)["name"] for child in layer.get("children", []))


def frames(design: Design) -> Value:
    return [
        (f["name"], box(f), colours(f.get("fills")), children(design, f))
        for f in design.layers()
        if f["type"] == "frame"
    ]


def shapes(design: Design) -> Value:
    return [(s["type"], s["name"], box(s)) for s in design.layers()]


def text(design: Design) -> Value:
    """Each text layer's words, and its font where it names one."""
    return [
        (
            t["characters"],
            t.get("style", {}).get("font_family"),
            t.get("style", {}).get("font_size"),
        )
        for t in design.layers()
        if t["type"] == "text"
    ]


def fills_and_strokes(design: Design) -> Value:
    return [
        (
            s["name"],
            colours(s.get("fills")),
            colours(s.get("strokes")),
            s.get("stroke", {}).get("weight") if s.get("strokes") else None,
        )
        for s in design.layers()
    ]


def groups(design: Design) -> Value:
    return [(g["name"], children(design, g)) for g in design.layers() if g["type"] == "group"]


def pages(design: Design) -> Value:
    return [(page["name"], children(design, page)) for page in design.pages()]


def components(design: Design) -> Value:
    """Each component, and each instance with the name of the component it is of."""
    return [
        (
            c["type"],
            c["name"],
            box(c),
            design.node(c["component"])["name"] if "component" in c else None,
        )
        for c in design.layers()
        if c["type"] in {"component", "instance"}
    ]


def auto_layout(design: Design) -> Value:
    found: Value = []
    for frame in design.layers():
        layout = frame.get("layout") or {}
        if layout:
            padding = tuple(number(p) for p in layout.get("padding", []))
            found.append((frame["name"], layout["mode"], number(layout.get("gap", 0)), padding))
    return found


def comments(design: Design) -> Value:
    return [
        (c["author"], c["text"], c["resolved"], number(c["x"]), number(c["y"]))
        for c in design.document.get("comments", [])
    ]


def variables(design: Design) -> Value:
    """Each variable's collection, name, type and values, by mode name rather than mode id."""
    held = design.document.get("variables", {})
    collections = {c["id"]: c for c in held.get("collections", [])}
    found: Value = []
    for variable in held.get("variables", []):
        collection = collections[variable["collection"]]
        modes = {mode["id"]: mode["name"] for mode in collection["modes"]}
        values = sorted((modes[m], v["value"]) for m, v in variable["values"].items())
        found.append(
            (collection["name"], variable["name"], variable["resolvedType"], tuple(values))
        )
    return found


def styles(design: Design) -> Value:
    """Each style's name and paints, and which layers use it, by name."""
    defined = {s["id"]: s for s in design.document.get("styles", [])}
    found: Value = [(s["name"], s["type"], colours(s.get("paints"))) for s in defined.values()]
    for layer in design.layers():
        for use, ref in (layer.get("styles") or {}).items():
            if ref:
                found.append((layer["name"], use, defined[ref]["name"]))
    return found


READERS: Final[dict[str, Callable[[Design], Value]]] = {
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


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a `.figcraft`."""
    return READERS[feature](Design(content))
