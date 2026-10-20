"""What the adapter reads from a design itself: whether it is a `.figcraft`, by its document.

A `.figcraft` is a zip holding its document as JSON, `document.json`, which says it is one by its
`format`. FigCraft also opens a `.fig`, its JSON, an SVG and images, and saves each as a
`.figcraft`, so the adapter opens only what is one already: nothing is converted.
"""

import io
import re
import zipfile
import zlib
from typing import Final

from artifactr.files.manifest import FIGCRAFT

DOCUMENT: Final = "document.json"
"""The part that holds the design."""

HEAD: Final = 256
"""How many of the document's first bytes its format is read from, inflating no more."""

FORMAT: Final = re.compile(rb'\A\s*\{\s*"format"\s*:\s*"figcraft"')
"""The document's start, as FigCraft writes it: its `format` first."""


def media_type(content: bytes) -> str | None:
    """`FIGCRAFT` if the bytes are a zip whose document says it is one, else None."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive, archive.open(DOCUMENT) as document:
            head = document.read(HEAD)
    except (zipfile.BadZipFile, KeyError, zlib.error, EOFError, NotImplementedError, RuntimeError):
        # Not a zip, no document, a corrupt deflate stream, or an encrypted or unknown part.
        return None
    return FIGCRAFT if FORMAT.match(head) else None
