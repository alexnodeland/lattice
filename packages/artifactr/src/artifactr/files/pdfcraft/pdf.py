"""What the adapter reads from a `.pdf`: its fingerprint, its format, and its outline.

PdfCraft stamps the time on every save, as its information dictionary's `/ModDate`, which it
writes in a compressed object stream, so the bytes of two saves of the same document differ
there, in that stream's length, and in where the objects after it lie. The fingerprint is the
digest of the file without them: each object stream read as what it holds, the stamp blanked,
and the cross-reference stream and `startxref`, which only say where the objects lie, left out.
"""

import hashlib
import re
import zlib
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel

from artifactr.files.app import AppFailed
from artifactr.files.manifest import OUTLINE_LIMIT, PDF

HEADER: Final = 1024
"""How far into a file its `%PDF-` header may be, as readers allow."""

MARK: Final = re.compile(rb"(?P<obj>(?<!\d)\d+\s+\d+\s+obj\b)|(?P<stream>stream\r?\n)|endobj")
"""Where an object starts, where its stream starts, and where it ends: found in one pass."""

LENGTH: Final = re.compile(rb"/Length\s+(\d+)(?!\d|\s+\d+\s+R)")
"""A stream's length, given directly: one given by a reference is left as written."""

XREF: Final = re.compile(rb"/Type\s*/XRef\b")
PACKED: Final = re.compile(rb"/Type\s*/ObjStm\b")
"""An object stream: the objects PdfCraft packs together, its stamp among them."""

DEFLATED: Final = re.compile(rb"/Filter\s*/FlateDecode\b")

STAMPED: Final = re.compile(rb"/ModDate\s*\((?:\\.|[^\\)])*\)")
"""What every save stamps: the information dictionary's modification date. It is blanked
wherever it is written, which is only there: an annotation's date is `/M`."""

WHERE: Final = re.compile(rb"startxref\s+\d+")


def media_type(content: bytes) -> str | None:
    """`application/pdf` if the file has a PDF's header, or None if it says no format."""
    return PDF if b"%PDF-" in content[:HEADER] else None


def fingerprint(content: bytes, *, limit: int) -> str:
    """The digest of a `.pdf` without what each save stamps, or where its objects lie.

    It leaves out exactly what PdfCraft's saves change, and reads any other file the same way,
    in one pass over its bytes. Only an object stream deflated by `/FlateDecode`, with its length
    given directly, is read as what it holds; every other stream is hashed as it is written.
    Each object stream is inflated as it is read, so one that inflates past `limit` is refused.

    Raises:
        AppFailed: `refused` if an object stream isn't deflated whole, and `too_large` if the
            object streams, inflated, pass `limit` bytes.
    """
    kept: list[bytes] = []
    budget = limit
    at = 0
    opened: re.Match[bytes] | None = None
    for mark in MARK.finditer(content):
        if mark.start() < at:
            continue  # within a stream already read
        if mark["obj"]:
            opened = mark
            continue
        if not mark["stream"] or opened is None:
            opened = None  # an object's end, or a stream no object opened
            continue
        head, start, opened = content[opened.end() : mark.start()], opened.start(), None
        packed = PACKED.search(head) and DEFLATED.search(head)
        if not (length := LENGTH.search(head)) or not (packed or XREF.search(head)):
            continue  # a stream kept as it is written
        data = content[mark.end() : mark.end() + int(length[1])]
        kept.append(content[at:start])
        if packed:
            held = _inflated(data, budget)
            budget -= len(held)
            kept.append(held)
        at = mark.end() + len(data)
    kept.append(content[at:])
    return hashlib.sha256(WHERE.sub(b"", STAMPED.sub(b"", b"".join(kept)))).hexdigest()


def _inflated(data: bytes, budget: int) -> bytes:
    """A deflated stream's bytes, whole, refused once they pass the budget."""
    inflater = zlib.decompressobj()
    try:
        held = inflater.decompress(data, max(budget, 1))
    except zlib.error as error:
        raise AppFailed("refused", f"not a .pdf: an object stream is {error}") from None
    if inflater.unconsumed_tail or len(held) > budget:
        raise AppFailed("too_large", "its object streams inflate past their limit")
    if not inflater.eof:
        raise AppFailed("refused", "not a .pdf: an object stream is cut short")
    return held


class Bookmark(BaseModel):
    """A bookmark of `doc_inspect`'s outline, and those under it."""

    title: str = ""
    children: list["Bookmark"] = []


def outline(bookmarks: Sequence[Bookmark], *, level: int = 0) -> str:
    """The bookmarks, each indented under its parent."""
    lines: list[str] = []
    for bookmark in bookmarks:
        lines.append("  " * level + bookmark.title)
        if bookmark.children:
            lines.append(outline(bookmark.children, level=level + 1))
    return "\n".join(lines)[:OUTLINE_LIMIT]
