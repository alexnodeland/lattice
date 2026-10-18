"""What the adapter reads from a `.docx` itself: its fingerprint, its format, and its outline.

A `.docx` is a zip of XML parts. WordCraft stamps `docProps/core.xml` with the time, a revision
count and the author on every save, so the fingerprint is the digest of the other parts: two
saves of the same document share it.
"""

import hashlib
import io
import re
import zipfile
import zlib
from collections.abc import Sequence
from typing import Final
from xml.etree import ElementTree

from pydantic import BaseModel

from artifactr.files.app import AppFailed
from artifactr.files.manifest import DOCX, OUTLINE_LIMIT

HEADING: Final = re.compile(r"heading ?(\d+)", re.IGNORECASE)
"""A heading's style, by its id or its name: `Heading1` or `heading 1`."""

STAMPED: Final = frozenset({"docProps/core.xml"})
"""The parts every save stamps, which the fingerprint leaves out."""

CHUNK: Final = 1 << 16

MAIN: Final = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml": DOCX,
    "application/vnd.ms-word.document.macroEnabled.main+xml": (
        "application/vnd.ms-word.document.macroEnabled.12"
    ),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.template"
    ),
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml": (
        "application/vnd.ms-word.template.macroEnabled.12"
    ),
}
"""A Word package's main part's content type, and the media type of a file it is the main of."""

TYPES: Final = "{http://schemas.openxmlformats.org/package/2006/content-types}Override"

MIMETYPE: Final = 255
"""The most of an OpenDocument's `mimetype` that is read."""


def media_type(content: bytes) -> str | None:
    """The format a package says it is, or None if it says none.

    A Word package says it by its main part's content type, and an OpenDocument by its
    `mimetype`. Call it once `fingerprint` has read the package, which refuses one that isn't
    a zip or inflates past its limit.

    Raises:
        AppFailed: `refused` if its content types aren't XML.
    """
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        if "mimetype" in names:
            return archive.read("mimetype")[:MIMETYPE].decode("ascii", "replace").strip()
        if "[Content_Types].xml" not in names:
            return None
        try:
            types = ElementTree.fromstring(archive.read("[Content_Types].xml"))
        except ElementTree.ParseError as error:
            raise AppFailed("refused", f"not a .docx: its content types are {error}") from None
    declared = (override.get("ContentType", "") for override in types.iter(TYPES))
    return next((MAIN[found] for found in declared if found in MAIN), None)


def fingerprint(content: bytes, *, limit: int) -> str:
    """The digest of a `.docx`'s parts, by name, without the parts each save stamps.

    Each part is hashed on its own, and the fingerprint is the digest of the parts' names and
    digests, so no two different files share one. Each part is read as it inflates, so a zip
    bomb is refused once it passes `limit`.

    Raises:
        AppFailed: `refused` if the bytes aren't a zip, or name a part twice, and `too_large` if
            its parts, inflated, pass `limit` bytes.
    """
    digest = hashlib.sha256()
    inflated = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = archive.namelist()
            if len(set(names)) != len(names):
                raise AppFailed("refused", "not a .docx: it names a part twice")
            for name in sorted(set(names) - STAMPED):
                part = hashlib.sha256()
                with archive.open(name) as stream:
                    while chunk := stream.read(CHUNK):
                        inflated += len(chunk)
                        if inflated > limit:
                            raise AppFailed("too_large", f"its parts inflate past {limit} bytes")
                        part.update(chunk)
                digest.update(f"{len(name)}:{name}".encode() + part.digest())
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError) as error:
        # A corrupt deflate stream is zlib's error, and an encrypted part zipfile's RuntimeError.
        raise AppFailed("refused", f"not a .docx: {error}") from None
    return digest.hexdigest()


class Block(BaseModel):
    """A block of `inspect_document`'s structure, as far as the outline reads it."""

    text: str = ""
    style: str | None = None


def outline(blocks: Sequence[Block]) -> str:
    """The headings among the blocks, indented by level, or else every block's first line.

    A title counts as a heading of the first level.
    """
    headings: list[str] = []
    lines: list[str] = []
    for block in blocks:
        if not block.text.strip():
            continue
        first = block.text.strip().splitlines()[0]
        lines.append(first)
        if (level := _level(block.style)) is not None:
            headings.append("  " * (level - 1) + first)
    return "\n".join(headings or lines)[:OUTLINE_LIMIT]


def _level(style: str | None) -> int | None:
    """A heading style's level, from 1: `Title`, then `Heading1` or `heading 1` to `Heading9`."""
    if (style or "").lower() == "title":
        return 1
    if found := HEADING.fullmatch(style or ""):
        return min(max(int(found[1]), 1), 9)
    return None
