"""A PNG of one colour, written without an imaging library: a blank page, or a fake's render."""

import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
"""The bytes every PNG starts with."""


def solid(width: int, height: int, rgb: bytes) -> bytes:
    """A `width` by `height` PNG, every pixel the 3-byte colour `rgb`."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + rgb * width
    return (
        SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )
