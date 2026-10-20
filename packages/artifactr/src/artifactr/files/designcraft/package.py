"""What the adapter reads from a layout itself: its format, IDML, told by its `mimetype`.

An IDML package is a zip whose `mimetype` entry names it. DesignCraft also opens its own JSON and
InDesign's `.indd`, which it converts to IDML, so the adapter gives it only what says it is IDML,
and saves it as IDML: a check-in never converts it.
"""

import io
import zipfile
import zlib
from typing import Final

from artifactr.files.manifest import IDML

MIMETYPE: Final = 255
"""The most of a package's `mimetype` that is read: never the whole of a part that inflates."""


def media_type(content: bytes) -> str | None:
    """IDML if the bytes are a zip whose `mimetype` says so, or else None."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive, archive.open("mimetype") as part:
            declared = part.read(MIMETYPE)
    except (zipfile.BadZipFile, KeyError, zlib.error, EOFError, NotImplementedError, RuntimeError):
        # A part that isn't there is zipfile's KeyError, and an encrypted one its RuntimeError.
        return None
    return IDML if declared.decode("ascii", "replace").strip() == IDML else None
