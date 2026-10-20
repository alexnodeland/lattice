"""PhotoCraft's corpus: one generated `.psd` per feature, beside this, each holding that feature.

Every file is written by hand, section by section, as the smallest 8-bit RGB `.psd` that holds
its feature, its pixels uncompressed, so the same code makes the same bytes. A test fails if the
committed files drift from what this makes; `python -m tests.files.corpus.photocraft.make`, from
`packages/artifactr`, writes them again.
"""

import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

HERE: Final = Path(__file__).parent
WIDTH: Final = 8
HEIGHT: Final = 6

RGBA = tuple[int, int, int, int]

CLOSE: Final = 3
"""A group's end, the `lsct` section type its divider is, below its layers."""

OPEN: Final = 1
"""A group's start, the `lsct` section type of the group's own record, above its layers."""


@dataclass(frozen=True)
class Layer:
    """A layer: its name, its colour over its bounds, and how it is drawn."""

    name: str
    colour: RGBA = (0, 0, 0, 0)
    bounds: tuple[int, int, int, int] = (0, 0, 0, 0)
    """Top, left, bottom and right, in pixels."""

    blend: bytes = b"norm"
    opacity: int = 255
    visible: bool = True
    section: int | None = None
    """Its `lsct` section type, for a group's record or its divider."""

    mask: tuple[int, int, int, int] | None = None
    """A layer mask's bounds, white within them over a black default."""


def pascal(name: str, *, pad: int) -> bytes:
    """A Pascal string, padded to a multiple of `pad` bytes, its length byte included."""
    raw = name.encode("latin-1")
    data = bytes([len(raw)]) + raw
    return data + b"\0" * (-len(data) % pad)


def block(data: bytes) -> bytes:
    """Data after its length, four bytes."""
    return struct.pack(">I", len(data)) + data


def channels(layer: Layer) -> list[tuple[int, bytes]]:
    """Each channel's id and its raw pixels: red, green, blue, alpha, and a mask's."""
    top, left, bottom, right = layer.bounds
    area = (bottom - top) * (right - left)
    found = [
        (i, bytes([value]) * area) for i, value in zip((0, 1, 2, -1), layer.colour, strict=True)
    ]
    if layer.mask is not None:
        mtop, mleft, mbottom, mright = layer.mask
        found.append((-2, b"\xff" * ((mbottom - mtop) * (mright - mleft))))
    return found


def record(layer: Layer) -> bytes:
    """A layer's record: its bounds, its channels' lengths, its blend, and its extra data."""
    held = channels(layer)
    mask = b""
    if layer.mask is not None:
        mask = struct.pack(">4iBB2x", *layer.mask, 0, 0)
    extra = block(mask) + block(b"") + pascal(layer.name, pad=4)
    if layer.section is not None:
        extra += b"8BIMlsct" + block(struct.pack(">I", layer.section))
    return (
        struct.pack(">4iH", *layer.bounds, len(held))
        + b"".join(struct.pack(">hI", i, 2 + len(pixels)) for i, pixels in held)
        + b"8BIM"
        + layer.blend
        + bytes([layer.opacity, 0, 0 if layer.visible else 2, 0])
        + block(extra)
    )


def psd(
    layers: Sequence[Layer], *, resolution: int = 72, background: RGBA = (255, 255, 255, 255)
) -> bytes:
    """A `.psd` of its layers, listed top to bottom, over a composite of the background."""
    header = b"8BPS" + struct.pack(">H6xHIIHH", 1, 3, HEIGHT, WIDTH, 8, 3)
    fixed = struct.pack(">IHH", resolution << 16, 1, 1)
    resources = b"8BIM" + struct.pack(">H", 1005) + pascal("", pad=2) + block(fixed * 2)
    bottom_up = list(reversed(layers))
    info = struct.pack(">h", len(bottom_up)) + b"".join(record(layer) for layer in bottom_up)
    info += b"".join(b"\0\0" + pixels for layer in bottom_up for _, pixels in channels(layer))
    info += b"\0" * (len(info) % 2)
    composite = b"\0\0" + b"".join(bytes([value]) * (WIDTH * HEIGHT) for value in background[:3])
    return header + block(b"") + block(resources) + block(block(info) + block(b"")) + composite


FULL: Final = (0, 0, HEIGHT, WIDTH)


def pixel_layers() -> bytes:
    return psd(
        [
            Layer("Red square", (255, 0, 0, 255), (1, 1, 4, 4)),
            Layer("Blue bar", (0, 0, 255, 255), (4, 0, 6, 8)),
            Layer("Background", (255, 255, 255, 255), FULL),
        ]
    )


def visibility_and_opacity() -> bytes:
    return psd(
        [
            Layer("Hidden", (0, 255, 0, 255), (0, 0, 3, 3), visible=False),
            Layer("Half", (255, 0, 0, 255), (2, 2, 5, 5), opacity=128),
            Layer("Background", (255, 255, 255, 255), FULL),
        ]
    )


def blend_modes() -> bytes:
    return psd(
        [
            Layer("Multiply", (255, 0, 0, 255), (0, 0, 3, 8), blend=b"mul "),
            Layer("Screen", (0, 0, 255, 255), (3, 0, 6, 8), blend=b"scrn"),
            Layer("Background", (128, 128, 128, 255), FULL),
        ]
    )


def groups() -> bytes:
    return psd(
        [
            Layer("Shapes", section=OPEN),
            Layer("Inside", (255, 0, 0, 255), (1, 1, 3, 3)),
            Layer("</Layer group>", section=CLOSE),
            Layer("Background", (255, 255, 255, 255), FULL),
        ]
    )


def layer_masks() -> bytes:
    return psd(
        [
            Layer("Masked", (0, 0, 255, 255), FULL, mask=(1, 1, 5, 7)),
            Layer("Background", (255, 255, 255, 255), FULL),
        ]
    )


def resolution() -> bytes:
    return psd([Layer("Background", (255, 255, 255, 255), FULL)], resolution=300)


FEATURES: Final[dict[str, Callable[[], bytes]]] = {
    "pixel_layers": pixel_layers,
    "visibility_and_opacity": visibility_and_opacity,
    "blend_modes": blend_modes,
    "groups": groups,
    "layer_masks": layer_masks,
    "resolution": resolution,
}
"""Each feature PhotoCraft's report compares, and what makes its file."""


def main() -> None:
    for feature, make in FEATURES.items():
        (HERE / f"{feature}.psd").write_bytes(make())


if __name__ == "__main__":
    main()
