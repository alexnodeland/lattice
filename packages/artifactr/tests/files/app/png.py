"""A PNG's size and first pixel, and a script's refusals: for adapters drawing a blank page."""

import ast
import struct
import zlib
from pathlib import Path


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


def refusals(script: Path, function: str) -> list[str]:
    """The words of each `raise Refused("...")` in a script's function, as it raises them."""
    tree = ast.parse(script.read_text())
    [found] = [f for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.name == function]
    return [
        raised.exc.args[0].value
        for raised in ast.walk(found)
        if isinstance(raised, ast.Raise)
        and isinstance(raised.exc, ast.Call)
        and isinstance(raised.exc.func, ast.Name)
        and raised.exc.func.id == "Refused"
        and raised.exc.args
        and isinstance(raised.exc.args[0], ast.Constant)
        and isinstance(raised.exc.args[0].value, str)
    ]
