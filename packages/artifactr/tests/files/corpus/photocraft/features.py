"""Each feature of a `.psd`, read out of its sections into a value that two saves can compare.

A value keeps what the feature means and leaves out what a save may rewrite without changing
it: how pixels are compressed, a layer's bounds cropped or grown round the same pixels, and the
resources and extra data a save adds. The fidelity report opens and saves each corpus file in
PhotoCraft and compares its feature's value before and after (lattice RFC-0003, phase 2).
"""

import hashlib
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

Value = list[tuple[object, ...]]

DIVIDER: Final = 3
"""The `lsct` section type of a group's end."""


def unpack(data: bytes, rows: int, width: int) -> bytes:
    """A channel's pixels, raw or PackBits, by its compression's first two bytes."""
    compression, data = struct.unpack(">H", data[:2])[0], data[2:]
    if compression == 0:
        return data
    counts = struct.unpack(f">{rows}H", data[: 2 * rows])
    out = bytearray()
    at = 2 * rows
    for count in counts:
        row, end = bytearray(), at + count
        while at < end:
            n = data[at]
            at += 1
            if n < 128:
                row += data[at : at + n + 1]
                at += n + 1
            elif n > 128:
                row += data[at : at + 1] * (257 - n)
                at += 1
        out += row[:width]
    return bytes(out)


@dataclass
class Layer:
    """A layer's record and its pixels, by canvas position."""

    name: str
    blend: str
    opacity: int
    visible: bool
    section: int | None
    mask: tuple[int, int, int, int, int] | None
    pixels: dict[tuple[int, int], tuple[int, ...]]
    masked: dict[tuple[int, int], int]


class Psd:
    """A `.psd`'s size, resolution and layers, top to bottom."""

    def __init__(self, content: bytes) -> None:
        self.height, self.width = struct.unpack(">II", content[14:22])
        at = 26
        at += 4 + struct.unpack(">I", content[at : at + 4])[0]
        size = struct.unpack(">I", content[at : at + 4])[0]
        self.resources = content[at + 4 : at + 4 + size]
        at += 4 + size + 4 + 4
        count = abs(struct.unpack(">h", content[at : at + 2])[0])
        at += 2
        records: list[tuple[tuple[int, ...], list[tuple[int, int]], Layer]] = []
        for _ in range(count):
            bounds = struct.unpack(">4i", content[at : at + 16])
            held = struct.unpack(">H", content[at + 16 : at + 18])[0]
            at += 18
            lengths = [
                struct.unpack(">hI", content[at + 6 * i : at + 6 * i + 6]) for i in range(held)
            ]
            at += 6 * held
            blend = content[at + 4 : at + 8].decode("latin-1")
            opacity, _, flags = content[at + 8], content[at + 9], content[at + 10]
            extra = struct.unpack(">I", content[at + 12 : at + 16])[0]
            data = content[at + 16 : at + 16 + extra]
            at += 16 + extra
            masklen = struct.unpack(">I", data[:4])[0]
            mask = struct.unpack(">4iB", data[4:21]) if masklen >= 20 else None
            rest = data[4 + masklen :]
            rest = rest[4 + struct.unpack(">I", rest[:4])[0] :]
            name = rest[1 : 1 + rest[0]].decode("latin-1")
            rest = rest[(1 + rest[0] + 3) // 4 * 4 :]
            section = None
            while len(rest) >= 12:
                key, length = rest[4:8], struct.unpack(">I", rest[8:12])[0]
                if key in (b"lsct", b"lsdk"):
                    section = struct.unpack(">I", rest[12:16])[0]
                rest = rest[12 + length + length % 2 :]
            layer = Layer(name, blend, opacity, not flags & 2, section, mask, {}, {})
            records.append((bounds, lengths, layer))
        for bounds, lengths, layer in records:
            planes: dict[int, bytes] = {}
            for channel, length in lengths:
                top, left, bottom, right = (
                    layer.mask[:4] if channel == -2 and layer.mask else bounds
                )
                planes[channel] = unpack(content[at : at + length], bottom - top, right - left)
                at += length
            top, left, bottom, right = bounds
            width = right - left
            for i in range((bottom - top) * width):
                pixel = tuple(planes[c][i] for c in (0, 1, 2, -1) if c in planes)
                if len(pixel) < 4 or pixel[3]:
                    layer.pixels[(left + i % width, top + i // width)] = pixel
            if layer.mask and -2 in planes:
                mtop, mleft, _, mright, _ = layer.mask
                for i, value in enumerate(planes[-2]):
                    if value != layer.mask[4]:
                        layer.masked[
                            (mleft + i % (mright - mleft), mtop + i // (mright - mleft))
                        ] = value
        self.layers = [layer for _, _, layer in reversed(records)]

    def resource(self, number: int) -> bytes:
        at = 0
        while at + 12 <= len(self.resources):
            found = struct.unpack(">H", self.resources[at + 4 : at + 6])[0]
            name = self.resources[at + 6]
            at += 6 + (1 + name + 1) // 2 * 2
            size = struct.unpack(">I", self.resources[at : at + 4])[0]
            if found == number:
                return self.resources[at + 4 : at + 4 + size]
            at += 4 + size + size % 2
        return b""

    def drawn(self) -> list[Layer]:
        """The layers that hold pixels: neither a group's record nor its end."""
        return [layer for layer in self.layers if layer.section is None]


def digest(pixels: dict[tuple[int, int], object]) -> str:
    return hashlib.sha256(repr(sorted(pixels.items())).encode()).hexdigest()


def pixel_layers(psd: Psd) -> Value:
    return [(layer.name, digest(dict(layer.pixels))) for layer in psd.drawn()]


def visibility_and_opacity(psd: Psd) -> Value:
    return [(layer.name, layer.visible, layer.opacity) for layer in psd.drawn()]


def blend_modes(psd: Psd) -> Value:
    return [(layer.name, layer.blend) for layer in psd.drawn()]


def groups(psd: Psd) -> Value:
    """Each layer's name, with the groups it is in, outermost first."""
    found: Value = []
    path: list[str] = []
    for layer in psd.layers:
        if layer.section == DIVIDER:
            path.pop()
        elif layer.section is not None:
            path.append(layer.name)
        else:
            found.append((tuple(path), layer.name))
    return found


def layer_masks(psd: Psd) -> Value:
    """Each mask's default colour and the pixels it holds otherwise, by canvas position."""
    return [
        (layer.name, layer.mask[4], digest(dict(layer.masked)))
        for layer in psd.drawn()
        if layer.mask is not None
    ]


def resolution(psd: Psd) -> Value:
    """The size, and the resolution in pixels per inch, of resource 1005."""
    found = psd.resource(1005)
    horizontal, vertical = struct.unpack(">I4xI", found[:12]) if found else (0, 0)
    return [(psd.width, psd.height, horizontal >> 16, vertical >> 16)]


READERS: Final[dict[str, Callable[[Psd], Value]]] = {
    "pixel_layers": pixel_layers,
    "visibility_and_opacity": visibility_and_opacity,
    "blend_modes": blend_modes,
    "groups": groups,
    "layer_masks": layer_masks,
    "resolution": resolution,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a `.psd`."""
    return READERS[feature](Psd(content))
