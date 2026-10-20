"""What the adapter reads from a FreeCAD document before FreeCAD starts: whether it is one, safely.

An `.FCStd` is a zip holding `Document.xml`, the objects and their properties, a part for each
shape, and, from the GUI, `GuiDocument.xml`. Opening one in FreeCAD restores each Python feature's
proxy by importing the module it names, so a document is refused before FreeCAD sees it if it
holds a Python feature or proxy, a link to another file, or an object of a type outside FreeCAD's
own C++ workbenches below (native files ADR-0014). Its parts are read from the zip's directory and
its XML streamed, so nothing is inflated past the limit, and no DTD or entity is read.
"""

import hashlib
import io
import re
import zipfile
import zlib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final
from xml.parsers import expat

from artifactr.files.app import AppFailed

DOCUMENT: Final = "Document.xml"
GUI: Final = "GuiDocument.xml"
PARTS: Final = 1_000
"""The most parts a document may hold."""

XML_LIMIT: Final = 64 << 20
"""The most bytes `Document.xml` or `GuiDocument.xml` may inflate to."""

DEPTH: Final = 256
"""The deepest an element of either may be."""

TYPES: Final = ("App::", "Part::", "PartDesign::", "Sketcher::", "Spreadsheet::")
"""The object types a document may hold: FreeCAD's own, in C++, but a Python feature's."""

MODIFIED: Final = re.compile(
    rb'(<Property name="LastModifiedDate"[^>]*>\s*<String value=")[^"]*(")'
)
"""Where every save writes the time, which a fingerprint leaves out."""

CHUNK: Final = 1 << 16


@dataclass(frozen=True)
class Scanned:
    """A document that may be opened: the label its document was saved with, if any."""

    label: str | None


def scan(content: bytes, limit: int) -> Scanned:
    """Refuse what isn't a FreeCAD document, or holds Python, before FreeCAD is given it.

    Raises:
        AppFailed: `refused` if it isn't a document, or holds what would run Python;
            `too_large` if it would inflate past the limit.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            parts = archive.infolist()
            if len(parts) > PARTS:
                raise AppFailed("refused", f"not a FreeCAD document: more than {PARTS} parts")
            if sum(part.file_size for part in parts) > limit:
                raise AppFailed("too_large", f"it inflates to more than {limit} bytes")
            names = {part.filename for part in parts}
            if DOCUMENT not in names:
                raise AppFailed("refused", f"not a FreeCAD document: no {DOCUMENT}")
            label = _Reader(DOCUMENT).read(_inflated(archive, DOCUMENT))
            if GUI in names:
                _Reader(GUI).read(_inflated(archive, GUI))
    except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError):
        # Not a zip, a corrupt deflate stream, or an encrypted or unknown part.
        raise AppFailed("refused", "not a FreeCAD document: not a zip it can read") from None
    return Scanned(label)


def fingerprint(content: bytes) -> str:
    """The SHA-256 of every part's name and bytes, in order, without the time a save writes."""
    digest = hashlib.sha256()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for part in archive.infolist():
            data = archive.read(part)
            if part.filename == DOCUMENT:
                data = MODIFIED.sub(rb"\1\2", data, count=1)
            name = part.filename.encode()
            digest.update(len(name).to_bytes(8, "big") + name)
            digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def with_gui(saved: bytes, source: bytes | None) -> bytes:
    """The saved document, with the source's `GuiDocument.xml`, which FreeCAD's console drops.

    Colours, visibility and the camera are in it; the thumbnail isn't kept, since a batch may
    have made it stale.
    """
    if source is None:
        return saved
    with zipfile.ZipFile(io.BytesIO(source)) as given:
        if GUI not in given.namelist():
            return saved
        gui = given.getinfo(GUI), given.read(GUI)
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(saved)) as made,
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        archive.comment = made.comment
        for part in made.infolist():
            if part.filename != GUI:
                archive.writestr(part, made.read(part))
        archive.writestr(*gui)
    return buffer.getvalue()


def _inflated(archive: zipfile.ZipFile, name: str) -> Iterator[bytes]:
    """A part's bytes, a chunk at a time, refused past `XML_LIMIT` whatever its header says."""
    read = 0
    with archive.open(name) as part:
        while chunk := part.read(CHUNK):
            read += len(chunk)
            if read > XML_LIMIT:
                raise AppFailed("too_large", f"{name} inflates to more than {XML_LIMIT} bytes")
            yield chunk


class _Reader:
    """Streams one XML part, refusing what would run Python, and reads the document's label."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.path: list[tuple[str, str]] = []
        self.label: str | None = None
        self.parser = expat.ParserCreate()
        self.parser.StartDoctypeDeclHandler = self._refuse_dtd
        self.parser.EntityDeclHandler = self._refuse_dtd
        self.parser.StartElementHandler = self._start
        self.parser.EndElementHandler = self._end

    def read(self, chunks: Iterator[bytes]) -> str | None:
        try:
            for chunk in chunks:
                self.parser.Parse(chunk, False)
            self.parser.Parse(b"", True)
        except expat.ExpatError as error:
            raise AppFailed("refused", f"{self.name} isn't XML: {error}") from None
        return self.label

    def _refuse(self, why: str) -> None:
        raise AppFailed("refused", f"{self.name} {why}")

    def _refuse_dtd(self, *_: object) -> None:
        self._refuse("declares a DTD or an entity")

    def _start(self, tag: str, attributes: dict[str, str]) -> None:
        if not self.path and tag != "Document":
            self._refuse(f"is a {tag}, not a document")
        if len(self.path) >= DEPTH:
            self._refuse(f"nests elements more than {DEPTH} deep")
        kind = attributes.get("type", "")
        if tag == "Python" or "Python" in kind:
            self._refuse(f"holds Python: {kind or tag}")
        if tag.startswith("XLink") and attributes.get("file"):
            self._refuse(f"links to another file: {attributes['file']}")
        if tag == "Object" and kind and not kind.startswith(TYPES):
            self._refuse(f"holds an object of a type that isn't allowed: {kind}")
        # The document's own label: Document, Properties, Property name="Label", String.
        if tag == "String" and self.path[1:] == [("Properties", ""), ("Property", "Label")]:
            self.label = attributes.get("value")
        self.path.append((tag, attributes.get("name", "")))

    def _end(self, _: str) -> None:
        self.path.pop()
