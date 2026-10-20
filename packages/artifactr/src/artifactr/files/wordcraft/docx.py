"""What the adapter reads from a `.docx` itself: its fingerprint, its format, and its outline.

A `.docx` is a zip of XML parts. WordCraft stamps `docProps/core.xml` with the time, a revision
count and the author on every save, so the fingerprint is the digest of the other parts: two
saves of the same document share it.
"""

import re
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel

from artifactr.files.craft import Package
from artifactr.files.manifest import DOCX, OUTLINE_LIMIT

HEADING: Final = re.compile(r"heading ?(\d+)", re.IGNORECASE)
"""A heading's style, by its id or its name: `Heading1` or `heading 1`."""

STAMPED: Final = frozenset({"docProps/core.xml"})
"""The parts every save stamps, which the fingerprint leaves out."""

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

DOCX_PACKAGE: Final = Package(".docx", main=MAIN, stamped=STAMPED)


def media_type(content: bytes) -> str | None:
    """The format a Word package or an OpenDocument says it is, or None if it says none.

    As [`Package.media_type`][artifactr.files.craft.Package.media_type] reads it.
    """
    return DOCX_PACKAGE.media_type(content)


def fingerprint(content: bytes, *, limit: int) -> str:
    """The digest of a `.docx`'s parts, by name, without the parts each save stamps.

    As [`Package.fingerprint`][artifactr.files.craft.Package.fingerprint] reads it.
    """
    return DOCX_PACKAGE.fingerprint(content, limit=limit)


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
