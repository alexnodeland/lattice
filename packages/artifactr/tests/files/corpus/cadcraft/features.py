"""Each feature of a DXF, read out of its groups into a value that two saves can be compared by.

A value keeps what the feature means and leaves out what a save may rewrite without changing
it: handles, which are numbered again, the groups a newer DXF version adds, and the layers and
tables every drawing has. The fidelity report opens and saves each corpus file in CADCraft and
compares its feature's value before and after (lattice RFC-0003, phase 2).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

Value = list[tuple[object, ...]]

PLACES: Final = 6
"""The decimals a coordinate is compared to: a save writes floats its own way."""


@dataclass(frozen=True)
class Entity:
    """An entity, a table entry or a header variable: its type, and its groups in order."""

    kind: str
    groups: tuple[tuple[int, str], ...]

    def first(self, code: int, default: str = "") -> str:
        return next((value for c, value in self.groups if c == code), default)

    def all(self, code: int) -> list[str]:
        return [value for c, value in self.groups if c == code]

    def number(self, code: int, default: float = 0.0) -> float:
        found = self.first(code)
        return round(float(found), PLACES) if found else default

    def point(self, code: int) -> tuple[float, float]:
        return (self.number(code), self.number(code + 10))


class Dxf:
    """An ASCII DXF's sections, each a list of its entities, split at each group 0."""

    def __init__(self, content: bytes) -> None:
        lines = content.decode("utf-8", "replace").splitlines()
        groups = [(int(lines[i]), lines[i + 1].strip()) for i in range(0, len(lines) - 1, 2)]
        self.sections: dict[str, list[Entity]] = {}
        section: list[Entity] = []
        for code, value in groups:
            if code == 0 and value in {"SECTION", "ENDSEC", "EOF"}:
                section = []
            elif code == 2 and not section and value not in self.sections:
                self.sections[value] = section
                section.append(Entity("", ()))
            elif code == 0:
                section.append(Entity(value, ()))
            elif section:
                last = section[-1]
                section[-1] = Entity(last.kind, (*last.groups, (code, value)))

    def entities(self, *kinds: str, section: str = "ENTITIES") -> list[Entity]:
        return [e for e in self.sections.get(section, []) if e.kind in kinds]

    def header(self, variable: str) -> str:
        groups = self.sections.get("HEADER", [Entity("", ())])[0].groups
        following = (groups[i + 1][1] for i, g in enumerate(groups[:-1]) if g == (9, variable))
        return next(following, "")


def lines(dxf: Dxf) -> Value:
    return [(e.first(8), e.point(10), e.point(11)) for e in dxf.entities("LINE")]


def circles_and_arcs(dxf: Dxf) -> Value:
    return [
        (e.kind, e.point(10), e.number(40), e.number(50), e.number(51))
        for e in dxf.entities("CIRCLE", "ARC")
    ]


def polylines(dxf: Dxf) -> Value:
    """Each polyline's vertices and whether it is closed, its flag's first bit."""
    return [
        (
            int(e.first(70, "0")) & 1,
            [
                (round(float(x), PLACES), round(float(y), PLACES))
                for x, y in zip(e.all(10), e.all(20), strict=True)
            ],
        )
        for e in dxf.entities("LWPOLYLINE")
    ]


def text(dxf: Dxf) -> Value:
    """Each text's words, an MTEXT's chunks joined, where it stands and how tall it is."""
    return [
        (e.kind, "".join(e.all(3)) + e.first(1), e.point(10), e.number(40))
        for e in dxf.entities("TEXT", "MTEXT")
    ]


def layers(dxf: Dxf) -> Value:
    """Each entity's layer, with that layer's colour and line type."""
    defined = {e.first(2): e for e in dxf.entities("LAYER", section="TABLES")}
    found: Value = []
    for entity in dxf.entities("LINE"):
        layer = defined.get(entity.first(8), Entity("", ()))
        found.append((entity.first(8), abs(int(layer.first(62, "7"))), layer.first(6).upper()))
    return found


def blocks(dxf: Dxf) -> Value:
    """Each insert's block, where it stands and its rotation, and the entities the block holds."""
    held: dict[str, list[str]] = {}
    name = ""
    for entity in dxf.sections.get("BLOCKS", []):
        if entity.kind == "BLOCK":
            name = entity.first(2)
            held[name] = []
        elif entity.kind not in {"", "ENDBLK"}:
            held[name].append(entity.kind)
    return [
        (e.first(2), e.point(10), e.number(50), tuple(held.get(e.first(2), [])))
        for e in dxf.entities("INSERT")
    ]


def units(dxf: Dxf) -> Value:
    return [(dxf.header("$INSUNITS"),)]


READERS: Final[dict[str, Callable[[Dxf], Value]]] = {
    "lines": lines,
    "circles_and_arcs": circles_and_arcs,
    "polylines": polylines,
    "text": text,
    "layers": layers,
    "blocks": blocks,
    "units": units,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a DXF."""
    return READERS[feature](Dxf(content))
