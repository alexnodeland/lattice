"""What the adapter reads from a `.docx` itself: its fingerprint, and its outline.

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

from pydantic import BaseModel

from artifactr.files.app import AppFailed
from artifactr.files.manifest import OUTLINE_LIMIT

HEADING: Final = re.compile(r"heading ?(\d+)", re.IGNORECASE)
"""A heading's style, by its id or its name: `Heading1` or `heading 1`."""

STAMPED: Final = frozenset({"docProps/core.xml"})
"""The parts every save stamps, which the fingerprint leaves out."""

CHUNK: Final = 1 << 16


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
