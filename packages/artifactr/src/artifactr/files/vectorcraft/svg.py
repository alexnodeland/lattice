"""What the adapter reads from an SVG itself: whether it is one, by its root element.

VectorCraft opens PDF, Illustrator, EPS and many more, and saves what it is given as an SVG when
it is asked to, so the adapter gives it only an SVG: anything else would come back converted.
"""

import re
from typing import Final

from artifactr.files.manifest import SVG

HEAD: Final = 4096
"""How many of a file's first bytes its root element is looked for in."""

PROLOGUE: Final = re.compile(
    rb"\A(?:\xef\xbb\xbf)?\s*(?:<\?xml[^>]*\?>\s*)?"
    rb"(?:(?:<!--.*?-->|<!DOCTYPE\s+svg[^>\[]*(?:\[.*?\])?\s*>)\s*)*"
    rb"<(?:svg:)?svg[\s>/]",
    re.DOTALL,
)
"""An SVG's start: a declaration, comments and its doctype, its internal subset too, then its
root element, `svg`. What the subset declares is VectorCraft's to refuse."""


def media_type(content: bytes) -> str | None:
    """`image/svg+xml` if the bytes are an SVG, by their root element; None if they aren't.

    A gzipped SVG, `.svgz`, isn't: VectorCraft would save it uncompressed.
    """
    return SVG if PROLOGUE.match(content[:HEAD]) else None
