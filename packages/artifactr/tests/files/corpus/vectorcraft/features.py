"""Each feature of an SVG, read out of its elements into a value that two saves can compare.

A value keeps what the feature means and leaves out what a save may rewrite without changing
it: a shape's element, which VectorCraft writes as a path, a transform it bakes into the
geometry, a gradient's id and units. Shapes are compared by their bounds in the drawing's own
coordinates. The fidelity report opens and saves each corpus file in VectorCraft and compares
its feature's value before and after (lattice RFC-0003, phase 2).
"""

import math
import re
from collections.abc import Callable, Iterator
from typing import Final
from xml.etree import ElementTree

Value = list[tuple[object, ...]]
Matrix = tuple[float, float, float, float, float, float]

S: Final = "{http://www.w3.org/2000/svg}"
PLACES: Final = 2
"""The decimals a coordinate is compared to: a save writes curves' points to three."""

IDENTITY: Final[Matrix] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
SHAPES: Final = {f"{S}{tag}" for tag in ("rect", "circle", "path")}
NUMBER: Final = re.compile(r"-?[0-9]*\.?[0-9]+(?:e-?[0-9]+)?")
TRANSFORM: Final = re.compile(r"(matrix|translate|rotate)\(([^)]*)\)")


def multiply(m: Matrix, n: Matrix) -> Matrix:
    a, b, c, d, e, f = m
    p, q, r, s, t, u = n
    return (
        a * p + c * q,
        b * p + d * q,
        a * r + c * s,
        b * r + d * s,
        a * t + c * u + e,
        b * t + d * u + f,
    )


def matrix(transform: str) -> Matrix:
    """A transform attribute's matrix: its matrices, translations and rotations, in order."""
    found = IDENTITY
    for kind, numbers in TRANSFORM.findall(transform):
        n = [float(x) for x in NUMBER.findall(numbers)]
        if kind == "matrix":
            step: Matrix = (n[0], n[1], n[2], n[3], n[4], n[5])
        elif kind == "translate":
            step = (1.0, 0.0, 0.0, 1.0, n[0], n[1] if len(n) > 1 else 0.0)
        else:
            cos, sin = math.cos(math.radians(n[0])), math.sin(math.radians(n[0]))
            step = (cos, sin, -sin, cos, 0.0, 0.0)
        found = multiply(found, step)
    return found


def points(element: ElementTree.Element) -> list[tuple[float, float]]:
    """A shape's corners, or its path's points, control points among them."""

    def get(name: str) -> float:
        return float(element.get(name, "0"))

    if element.tag == f"{S}rect":
        x, y, w, h = get("x"), get("y"), get("width"), get("height")
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    if element.tag == f"{S}circle":
        cx, cy, r = get("cx"), get("cy"), get("r")
        return [(cx - r, cy - r), (cx + r, cy + r)]
    n = [float(x) for x in NUMBER.findall(element.get("d", ""))]
    return list(zip(n[::2], n[1::2], strict=False))


def walk(
    element: ElementTree.Element, at: Matrix = IDENTITY
) -> Iterator[tuple[ElementTree.Element, Matrix]]:
    """Every element, with the transform from its own coordinates to the drawing's."""
    for child in element:
        placed = multiply(at, matrix(child.get("transform", "")))
        yield child, placed
        yield from walk(child, placed)


def bounds(element: ElementTree.Element, at: Matrix) -> tuple[float, ...]:
    a, b, c, d, e, f = at
    moved = [(a * x + c * y + e, b * x + d * y + f) for x, y in points(element)]
    xs, ys = [x for x, _ in moved], [y for _, y in moved]
    return tuple(round(v, PLACES) + 0.0 for v in (min(xs), min(ys), max(xs), max(ys)))


def shapes(root: ElementTree.Element) -> Value:
    return sorted((e.get("id", ""), bounds(e, at)) for e, at in walk(root) if e.tag in SHAPES)


def paint(root: ElementTree.Element) -> Value:
    return sorted(
        (
            e.get("id", ""),
            e.get("fill", "#000000").lower(),
            e.get("stroke", "none").lower(),
            float(e.get("stroke-width", "1")),
            float(e.get("opacity", "1")),
        )
        for e, _ in walk(root)
        if e.tag in SHAPES
    )


def groups(root: ElementTree.Element) -> Value:
    """Each group, by id, and the ids of what it holds."""
    return sorted(
        (e.get("id", ""), tuple(sorted(child.get("id", "") for child in e)))
        for e, _ in walk(root)
        if e.tag == f"{S}g" and e.get("id") != "Layer_1"
    )


def text(root: ElementTree.Element) -> Value:
    """Each text's words, font and size, and where its first baseline starts."""
    found: Value = []
    for e, at in walk(root):
        if e.tag == f"{S}text":
            a, b, c, d, x0, y0 = at
            x, y = float(e.get("x", "0")), float(e.get("y", "0"))
            anchor = (round(a * x + c * y + x0, PLACES), round(b * x + d * y + y0, PLACES))
            words = "".join(e.itertext())
            found.append((words, e.get("font-family"), float(e.get("font-size", "0")), anchor))
    return sorted(found)


def gradients(root: ElementTree.Element) -> Value:
    """Each shape a gradient fills, and the gradient's kind and stops."""
    defined = {e.get("id", ""): e for e, _ in walk(root) if e.tag.endswith("Gradient")}
    found: Value = []
    for e, _ in walk(root):
        if e.tag in SHAPES and (fill := re.fullmatch(r"url\(#(.+)\)", e.get("fill", ""))):
            gradient = defined[fill[1]]
            stops = tuple(
                (float(s.get("offset", "0")), s.get("stop-color", "").lower())
                for s in gradient.iter(f"{S}stop")
            )
            found.append((e.get("id", ""), gradient.tag.removeprefix(S), stops))
    return sorted(found)


def size(root: ElementTree.Element) -> Value:
    return [(root.get("width"), root.get("height"), root.get("viewBox"))]


READERS: Final[dict[str, Callable[[ElementTree.Element], Value]]] = {
    "shapes": shapes,
    "paint": paint,
    "groups": groups,
    "text": text,
    "gradients": gradients,
    "transforms": shapes,
    "size": size,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in an SVG."""
    return READERS[feature](ElementTree.fromstring(content))
