"""VectorCraft's corpus: one generated `.svg` per feature, beside this, each holding that feature.

Every file is written by hand, as the smallest SVG that holds its feature, so the same code makes
the same bytes. A test fails if the committed files drift from what this makes;
`python -m tests.files.corpus.vectorcraft.make`, from `packages/artifactr`, writes them again.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Final

HERE: Final = Path(__file__).parent


def svg(body: str, *, width: int = 200, height: int = 100, head: str = "") -> bytes:
    """An SVG of a body, its size and its view box the same."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">{head}{body}</svg>\n'
    ).encode()


def shapes() -> bytes:
    return svg(
        '<rect id="box" x="10" y="10" width="80" height="40" fill="#cccccc"/>'
        '<circle id="dot" cx="150" cy="50" r="20" fill="#cccccc"/>'
        '<path id="wedge" d="M 100 90 L 140 60 L 180 90 Z" fill="#cccccc"/>'
    )


def paint() -> bytes:
    return svg(
        '<rect id="red" x="10" y="10" width="40" height="40" fill="#ff0000" stroke="#000000" '
        'stroke-width="2"/>'
        '<rect id="faint" x="60" y="10" width="40" height="40" fill="#0000ff" opacity="0.5"/>'
        '<rect id="outline" x="110" y="10" width="40" height="40" fill="none" stroke="#00aa00" '
        'stroke-width="4"/>'
    )


def groups() -> bytes:
    return svg(
        '<g id="Back"><rect id="sky" x="0" y="0" width="200" height="50" fill="#88ccff"/></g>'
        '<g id="Front"><g id="house"><rect id="wall" x="50" y="50" width="60" height="40" '
        'fill="#aa6633"/></g></g>'
    )


def text() -> bytes:
    return svg(
        '<text x="10" y="30" font-family="Helvetica" font-size="12" fill="#000000">Hello</text>'
        '<text x="10" y="60" font-family="Helvetica" font-size="18" fill="#000000">World</text>'
    )


def gradients() -> bytes:
    return svg(
        '<rect id="fade" x="10" y="10" width="180" height="80" fill="url(#ramp)"/>',
        head='<defs><linearGradient id="ramp" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff"/>'
        "</linearGradient></defs>",
    )


def transforms() -> bytes:
    return svg(
        '<rect id="turned" x="0" y="0" width="40" height="20" fill="#333333" '
        'transform="translate(100 50) rotate(45)"/>'
    )


def size() -> bytes:
    return svg(
        '<rect id="page" x="0" y="0" width="300" height="400" fill="#eeeeee"/>',
        width=300,
        height=400,
    )


FEATURES: Final[dict[str, Callable[[], bytes]]] = {
    "shapes": shapes,
    "paint": paint,
    "groups": groups,
    "text": text,
    "gradients": gradients,
    "transforms": transforms,
    "size": size,
}
"""Each feature VectorCraft's report compares, and what makes its file."""


def main() -> None:
    for feature, make in FEATURES.items():
        (HERE / f"{feature}.svg").write_bytes(make())


if __name__ == "__main__":
    main()
