"""A PNG's size and first pixel, for the tests of the adapters that draw a blank page."""

import struct
import zlib


def pixels(png: bytes) -> tuple[int, int, bytes]:
    """An 8-bit RGB or RGBA PNG's width, height and first pixel: three bytes, or four with alpha.

    The first pixel of the first row is its bytes whatever the row's filter, as nothing is above
    or left of it.
    """
    width, height = struct.unpack(">II", png[16:24])
    channels = 4 if png[25] == 6 else 3
    data, at = b"", 8
    while at < len(png):
        (length,) = struct.unpack(">I", png[at : at + 4])
        if png[at + 4 : at + 8] == b"IDAT":
            data += png[at + 8 : at + 8 + length]
        at += 12 + length
    return width, height, zlib.decompress(data)[1 : 1 + channels]
