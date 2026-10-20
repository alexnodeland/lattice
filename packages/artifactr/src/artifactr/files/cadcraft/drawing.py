"""What the adapter reads from a drawing itself: its format, DXF or DWG, told by its first bytes.

CADCraft opens both, and saves in the format of the name it is given, so the adapter names the
file by the format its bytes are, and saves it in the same one: a check-in never converts it.
"""

import re
from typing import Final

from artifactr.files.manifest import DWG, DXF

DWG_MAGIC: Final = re.compile(rb"AC10[0-9]{2}")
"""A DWG's first six bytes: its version, such as `AC1032` for AutoCAD 2018's."""

BINARY_DXF: Final = b"AutoCAD Binary DXF\r\n\x1a\x00"
"""A binary DXF's sentinel, its first 22 bytes."""

ASCII_DXF: Final = re.compile(
    rb"\A(?:\xef\xbb\xbf)?(?:\s*999\r?\n[^\n]*\n)*\s*0\r?\n\s*SECTION\r?\n"
)
"""An ASCII DXF's start: comments, then its first group, `0`, opening a `SECTION`."""

HEAD: Final = 4096
"""How many of a file's first bytes its format is read from."""

EXTENSIONS: Final = {DXF: ".dxf", DWG: ".dwg"}
"""Each format, and the extension CADCraft is given a file of it by, and saves it in."""


def media_type(content: bytes) -> str | None:
    """The drawing format the bytes are, DXF or DWG, or None if they are neither."""
    head = content[:HEAD]
    if DWG_MAGIC.match(head):
        return DWG
    if head.startswith(BINARY_DXF) or ASCII_DXF.match(head):
        return DXF
    return None
