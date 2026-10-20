"""What the adapter reads from an SVG itself: whether it is one, by its root element.

VectorCraft opens PDF, Illustrator, EPS and many more, and saves what it is given as an SVG when
it is asked to, so the adapter gives it only an SVG: anything else would come back converted.
"""

import re
from typing import Final

from artifactr.files.manifest import SVG

HEAD: Final = 4096
"""How many of a file's first bytes its root element is looked for in."""

BOM: Final = b"\xef\xbb\xbf"

DOCTYPE: Final = re.compile(rb"<!DOCTYPE\s+svg[\s>\[]")
"""An SVG's doctype, whose internal subset is VectorCraft's to refuse."""

ROOT: Final = re.compile(rb"<(?:svg:)?svg[\s>/]")
"""An SVG's root element, `svg`."""


def media_type(content: bytes) -> str | None:
    """`image/svg+xml` if the bytes are an SVG, by their root element; None if they aren't.

    A gzipped SVG, `.svgz`, isn't: VectorCraft would save it uncompressed.
    """
    return SVG if ROOT.match(_root(content[:HEAD].removeprefix(BOM))) else None


def _root(head: bytes) -> bytes:
    """What follows the prologue: its declaration, comments and doctype, each skipped in turn.

    Each is skipped by finding its end, not by a pattern over all of them, so no input makes
    the search backtrack.
    """
    while head := head.lstrip():
        if head.startswith((b"<?xml", b"<!--")):
            _, ended, head = head.partition(b"?>" if head.startswith(b"<?") else b"-->")
        elif DOCTYPE.match(head):
            opened, closed = head.find(b"["), head.find(b">")
            if 0 <= opened < closed:
                head = head[head.find(b"]", opened) + 1 :]
            _, ended, head = head.partition(b">")
        else:
            return head
        if not ended:
            return b""
    return head
