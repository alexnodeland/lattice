"""What the agent reads of a diagram: a short description computed from its elements (RFC-0006).

It is synchronous and does no IO, and is never stored: frames, shapes with their labels, arrows
as ``A --label--> B``, free text, counts and the bounding box, in at most
:data:`MAX_DESCRIPTION` characters. portalr's text alternative for a diagram is the same
description, ported, and held equal to it by a shared fixture.
"""

from collections.abc import Iterable, Mapping
from typing import Final

from pydantic import JsonValue

__all__ = ["MAX_DESCRIPTION", "describe"]

MAX_DESCRIPTION: Final = 4_000
"""The most characters a description holds."""

_SHAPES: Final = frozenset({"rectangle", "ellipse", "diamond", "image", "embeddable", "iframe"})
_LINES: Final = frozenset({"arrow", "line"})

Element = Mapping[str, JsonValue]


def describe(name: str, elements: Mapping[str, Element]) -> str:
    """Describe a diagram's live elements, as the agent and assistive technology read it."""
    live = {key: e for key, e in elements.items() if not e.get("isDeleted")}
    labels = _labels(live)
    frames: list[str] = []
    shapes: list[str] = []
    arrows: list[str] = []
    texts: list[str] = []
    for key, element in live.items():
        kind = str(element.get("type"))
        if kind in {"frame", "magicframe"}:
            frames.append(f"- {_name(element, key)}")
        elif kind in _SHAPES:
            shapes.append(f"- {kind} {_named(labels, key)}")
        elif kind in _LINES:
            arrows.append(f"- {_arrow(element, labels)}")
        elif kind == "text" and element.get("containerId") is None:
            texts.append(f"- {_quote(element.get('text'))}")
    lines = [f"Diagram {_quote(name)}: {len(live)} elements"]
    if (box := _box(live.values())) is not None:
        lines.append(f"Bounds: {box}")
    for title, part in (
        ("Frames", frames),
        ("Shapes", shapes),
        ("Arrows", arrows),
        ("Text", texts),
    ):
        if part:
            lines.extend([f"{title} ({len(part)}):", *part])
    return _cut("\n".join(lines))


def _labels(elements: Mapping[str, Element]) -> dict[str, str]:
    """Each container's label: the text bound inside it."""
    labels: dict[str, str] = {}
    for element in elements.values():
        container = element.get("containerId")
        if element.get("type") == "text" and isinstance(container, str):
            labels[container] = _quote(element.get("text"))
    return labels


def _named(labels: Mapping[str, str], key: str) -> str:
    return f"{key} {labels[key]}" if key in labels else key


def _name(element: Element, key: str) -> str:
    name = element.get("name")
    return f"{key} {_quote(name)}" if isinstance(name, str) and name else key


def _arrow(element: Element, labels: Mapping[str, str]) -> str:
    start = _bound(element.get("startBinding"))
    end = _bound(element.get("endBinding"))
    label = labels.get(str(element.get("id")))
    via = f"--{label}-->" if label else "-->"
    left = _named(labels, start) if start else "(free)"
    right = _named(labels, end) if end else "(free)"
    return f"{element.get('type')} {element.get('id')}: {left} {via} {right}"


def _bound(binding: JsonValue) -> str | None:
    if isinstance(binding, dict) and isinstance(binding.get("elementId"), str):
        return str(binding["elementId"])
    return None


def _box(elements: Iterable[Element]) -> str | None:
    edges: list[tuple[float, float, float, float]] = []
    for element in elements:
        x, y = element.get("x"), element.get("y")
        width, height = element.get("width", 0), element.get("height", 0)
        if (
            isinstance(x, int | float)
            and isinstance(y, int | float)
            and isinstance(width, int | float)
            and isinstance(height, int | float)
        ):
            edges.append((x, y, x + width, y + height))
    if not edges:
        return None
    left = min(e[0] for e in edges)
    top = min(e[1] for e in edges)
    right = max(e[2] for e in edges)
    bottom = max(e[3] for e in edges)
    return f"x {left:g} to {right:g}, y {top:g} to {bottom:g}"


def _quote(text: JsonValue) -> str:
    said = " ".join(str(text or "").split())
    return f'"{said[:80]}"'


def _cut(text: str) -> str:
    if len(text) <= MAX_DESCRIPTION:
        return text
    more = "\n… (cut: read the diagram for the rest)"
    return text[: MAX_DESCRIPTION - len(more)] + more
