"""What an adapter reads from a zip package itself: its fingerprint and the format it says it is.

WordCraft's, GridCraft's and DeckCraft's files are Office Open XML packages, zips of XML parts.
A [`Package`][artifactr.files.craft.Package] is one such format: the content types of its main
part, by which a file says which of those formats it is, and the parts its app stamps on
every save, which the fingerprint leaves out so that two saves of the same file share it.
"""

import hashlib
import io
import zipfile
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final
from xml.etree import ElementTree

from artifactr.files.app import AppFailed

CHUNK: Final = 1 << 16

TYPES: Final = "{http://schemas.openxmlformats.org/package/2006/content-types}Override"

XML_PARTS: Final = (".xml", ".rels")

PART: Final = 16 << 20
"""The most bytes of one XML part a canonical package reads in its canonical form."""

ELEMENTS: Final = 500_000
"""The most elements a canonical package's XML parts hold, together."""

DEPTH: Final = 256
"""The deepest an element of a canonical package's XML parts is nested."""
"""The names a package's XML parts end with."""

MIMETYPE: Final = 255
"""The most of an OpenDocument's `mimetype` that is read."""


@dataclass(frozen=True)
class Package:
    """A zip package format, as its app's adapter reads it."""

    extension: str
    """Its files' extension, such as `.docx`, which its refusals name."""

    main: Mapping[str, str]
    """Its main part's content types, and the media type of a file each is the main part of."""

    stamped: frozenset[str] = frozenset()
    """The parts its app stamps on every save, which the fingerprint leaves out."""

    canonical: bool = False
    """Whether the fingerprint reads each XML part in its canonical form (C14N 2.0), for an app
    whose saves write the same XML in more than one way, such as `<a:p/>` and `<a:p></a:p>`."""

    def media_type(self, content: bytes) -> str | None:
        """The format a package says it is, or None if it says none.

        An Office Open XML package says it by its main part's content type, and an OpenDocument
        by its `mimetype`, which can't claim one of this package's formats. Call it once
        `fingerprint` has read the package, which refuses one that isn't a zip or inflates past
        its limit.

        Raises:
            AppFailed: `refused` if its content types aren't XML.
        """
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "mimetype" in names:
                said = archive.read("mimetype")[:MIMETYPE].decode("ascii", "replace").strip()
                # Only an OpenDocument says its format so: one that says it is of this
                # package's formats is spoofing it, and says none.
                return None if said in self.main.values() else said
            if "[Content_Types].xml" not in names:
                return None
            try:
                types = ElementTree.fromstring(archive.read("[Content_Types].xml"))
            except ElementTree.ParseError as error:
                message = f"not a {self.extension}: its content types are {error}"
                raise AppFailed("refused", message) from None
        declared = (override.get("ContentType", "") for override in types.iter(TYPES))
        return next((self.main[found] for found in declared if found in self.main), None)

    def fingerprint(self, content: bytes, *, limit: int) -> str:
        """The digest of a package's parts, by name, without the parts each save stamps.

        Each part is hashed on its own, and the fingerprint is the digest of the parts' names
        and digests, so no two different files share one. Each part is read as it inflates, so
        a zip bomb is refused once it passes `limit`; a `canonical` package's XML parts are
        hashed in their canonical form.

        Raises:
            AppFailed: `refused` if the bytes aren't a zip, name a part twice, or, canonical,
                hold an XML part that isn't XML, and `too_large` if its parts, inflated, pass
                `limit` bytes.
        """
        digest = hashlib.sha256()
        inflated = 0
        elements = [ELEMENTS]
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = archive.namelist()
                if len(set(names)) != len(names):
                    raise AppFailed("refused", f"not a {self.extension}: it names a part twice")
                for name in sorted(set(names) - self.stamped):
                    part = hashlib.sha256()
                    xml = self.canonical and name.endswith(XML_PARTS)
                    kept: list[bytes] = []
                    if xml and archive.getinfo(name).file_size > PART:
                        message = f"{name} is larger than {PART} bytes"
                        raise AppFailed("too_large", message)
                    with archive.open(name) as stream:
                        while chunk := stream.read(CHUNK):
                            inflated += len(chunk)
                            if inflated > limit:
                                message = f"its parts inflate past {limit} bytes"
                                raise AppFailed("too_large", message)
                            if xml:
                                kept.append(chunk)
                            else:
                                part.update(chunk)
                    if xml:
                        part.update(self._canonical(name, b"".join(kept), elements))
                    digest.update(f"{len(name)}:{name}".encode() + part.digest())
        except (
            zipfile.BadZipFile,
            zlib.error,
            EOFError,
            NotImplementedError,
            RuntimeError,
        ) as error:
            # A corrupt deflate stream is zlib's error, and an encrypted part zipfile's
            # RuntimeError.
            raise AppFailed("refused", f"not a {self.extension}: {error}") from None
        return digest.hexdigest()

    def require(self, content: bytes, media_type: str, *, limit: int) -> None:
        """Refuse a file that doesn't say it is `media_type`, before its app opens it.

        For an app that opens other formats whatever a file is named, and saves what it opened
        in the format it is asked for: a file of another format is refused, never converted.

        Raises:
            AppFailed: `refused` if it isn't a zip, or says it is another format or none, and
                `too_large` if its parts, inflated, pass `limit` bytes.
        """
        self.fingerprint(content, limit=limit)
        if (found := self.media_type(content)) != media_type:
            raise AppFailed(
                "refused", f"not a {self.extension}: it says it is {found or 'no format'}"
            )

    def _canonical(self, name: str, part: bytes, elements: list[int]) -> bytes:
        """An XML part in its canonical form, the same however a save wrote it.

        Its elements are counted against what is left of the package's, `elements`.

        Raises:
            AppFailed: `refused` if it isn't XML or nests past `DEPTH`, and `too_large` if the
                package's parts hold more than `ELEMENTS` elements.
        """
        written: list[str] = []
        parser = ElementTree.XMLParser(target=_Bounded(written.append, elements, self, name))
        try:
            parser.feed(part)
            parser.close()
        except ElementTree.ParseError as error:
            raise AppFailed("refused", f"not a {self.extension}: {name} is {error}") from None
        return "".join(written).encode()


class _Bounded(ElementTree.C14NWriterTarget):
    """C14N 2.0's writer, refusing a part that nests too deep or holds too many elements."""

    def __init__(
        self, write: Callable[[str], object], elements: list[int], package: Package, name: str
    ) -> None:
        super().__init__(write)
        self._elements = elements
        self._depth = 0
        self._where = f"{name} of a {package.extension}"

    def start(self, tag: str, attrs: Mapping[str, str]) -> None:
        self._depth += 1
        self._elements[0] -= 1
        if self._elements[0] < 0:
            raise AppFailed("too_large", f"its XML parts hold more than {ELEMENTS} elements")
        if self._depth > DEPTH:
            raise AppFailed("refused", f"{self._where} nests deeper than {DEPTH}")
        super().start(tag, attrs)

    def end(self, tag: str) -> None:
        self._depth -= 1
        super().end(tag)
