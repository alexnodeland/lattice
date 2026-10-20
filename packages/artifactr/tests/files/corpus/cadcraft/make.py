"""CADCraft's corpus: one generated `.dxf` per feature, beside this, each holding that feature.

Every file is written by hand, group by group, as the smallest ASCII DXF that holds its feature,
so the same code makes the same bytes. A test fails if the committed files drift from what this
makes; `python -m tests.files.corpus.cadcraft.make`, from `packages/artifactr`, writes them again.
"""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

HERE: Final = Path(__file__).parent

Group = tuple[int, str | int | float]
"""A DXF group: its code, and its value."""


def dxf(
    entities: Sequence[Group],
    *,
    header: Sequence[Group] = (),
    layers: Sequence[Group] = (),
    blocks: Sequence[Group] = (),
) -> bytes:
    """An ASCII DXF of its entities, and of the header, layers and blocks they name."""
    groups: list[Group] = []
    for name, held in (
        ("HEADER", header),
        ("TABLES", [(0, "TABLE"), (2, "LAYER"), *layers, (0, "ENDTAB")] if layers else []),
        ("BLOCKS", blocks),
        ("ENTITIES", entities),
    ):
        if held or name == "ENTITIES":
            groups += [(0, "SECTION"), (2, name), *held, (0, "ENDSEC")]
    groups.append((0, "EOF"))
    return "".join(f"{code:>3}\n{value}\n" for code, value in groups).encode()


def point(code: int, x: float, y: float) -> list[Group]:
    """A point's three groups, its code's for x, and then y and z."""
    return [(code, x), (code + 10, y), (code + 20, 0.0)]


def lines() -> bytes:
    return dxf(
        [
            *[(0, "LINE"), (8, "0"), *point(10, 0.0, 0.0), *point(11, 100.0, 0.0)],
            *[(0, "LINE"), (8, "0"), *point(10, 100.0, 0.0), *point(11, 100.0, 50.0)],
        ]
    )


def circles_and_arcs() -> bytes:
    return dxf(
        [
            *[(0, "CIRCLE"), (8, "0"), *point(10, 50.0, 50.0), (40, 10.0)],
            *[(0, "ARC"), (8, "0"), *point(10, 0.0, 0.0), (40, 25.0), (50, 0.0), (51, 90.0)],
        ]
    )


def polylines() -> bytes:
    vertices = [(10.0, 10.0), (60.0, 10.0), (60.0, 40.0), (10.0, 40.0)]
    return dxf(
        [
            (0, "LWPOLYLINE"),
            (8, "0"),
            (90, len(vertices)),
            (70, 1),
            *[group for x, y in vertices for group in ((10, x), (20, y))],
        ]
    )


def text() -> bytes:
    return dxf(
        [
            *[(0, "TEXT"), (8, "0"), *point(10, 5.0, 5.0), (40, 2.5), (1, "Kitchen")],
            *[(0, "MTEXT"), (8, "0"), *point(10, 5.0, 20.0), (40, 2.5), (1, "Two\\Plines")],
        ]
    )


def layers() -> bytes:
    defined = [
        *[(0, "LAYER"), (2, "0"), (70, 0), (62, 7), (6, "CONTINUOUS")],
        *[(0, "LAYER"), (2, "Walls"), (70, 0), (62, 1), (6, "CONTINUOUS")],
        *[(0, "LAYER"), (2, "Doors"), (70, 0), (62, 3), (6, "CONTINUOUS")],
    ]
    return dxf(
        [
            *[(0, "LINE"), (8, "Walls"), *point(10, 0.0, 0.0), *point(11, 10.0, 0.0)],
            *[(0, "LINE"), (8, "Doors"), *point(10, 0.0, 5.0), *point(11, 10.0, 5.0)],
        ],
        layers=[(70, len(defined) // 5), *defined],
    )


def blocks() -> bytes:
    door = [
        *[(0, "BLOCK"), (8, "0"), (2, "Door"), (70, 0), *point(10, 0.0, 0.0), (3, "Door")],
        *[(0, "LINE"), (8, "0"), *point(10, 0.0, 0.0), *point(11, 0.0, 9.0)],
        *[(0, "ARC"), (8, "0"), *point(10, 0.0, 0.0), (40, 9.0), (50, 0.0), (51, 90.0)],
        *[(0, "ENDBLK"), (8, "0")],
    ]
    return dxf(
        [
            *[(0, "INSERT"), (8, "0"), (2, "Door"), *point(10, 20.0, 0.0)],
            *[(0, "INSERT"), (8, "0"), (2, "Door"), *point(10, 40.0, 0.0), (50, 90.0)],
        ],
        blocks=door,
    )


def units() -> bytes:
    return dxf(
        [(0, "LINE"), (8, "0"), *point(10, 0.0, 0.0), *point(11, 1000.0, 0.0)],
        header=[(9, "$INSUNITS"), (70, 4)],
    )


FEATURES: Final[dict[str, Callable[[], bytes]]] = {
    "lines": lines,
    "circles_and_arcs": circles_and_arcs,
    "polylines": polylines,
    "text": text,
    "layers": layers,
    "blocks": blocks,
    "units": units,
}
"""Each feature CADCraft's report compares, and what makes its file."""


def main() -> None:
    for feature, make in FEATURES.items():
        (HERE / f"{feature}.dxf").write_bytes(make())


if __name__ == "__main__":
    main()
