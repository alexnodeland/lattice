"""A PNG of one colour, written without an imaging library: a blank page, or a fake's render."""

import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
"""The bytes every PNG starts with."""


def solid(width: int, height: int, rgb: bytes) -> bytes:
    """A `width` by `height` PNG, every pixel the colour `rgb`: three bytes, or four with alpha.

    Raises:
        ValueError: If `rgb` isn't three or four bytes.
    """
    if len(rgb) not in {3, 4}:
        raise ValueError(f"a colour is three or four bytes, not {len(rgb)}")

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2 if len(rgb) == 3 else 6, 0, 0, 0)
    row = b"\x00" + rgb * width
    return (
        SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )
