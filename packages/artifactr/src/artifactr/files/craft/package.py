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
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from xml.etree import ElementTree

from artifactr.files.app import AppFailed

CHUNK: Final = 1 << 16

TYPES: Final = "{http://schemas.openxmlformats.org/package/2006/content-types}Override"

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

    def media_type(self, content: bytes) -> str | None:
        """The format a package says it is, or None if it says none.

        An Office Open XML package says it by its main part's content type, and an OpenDocument
        by its `mimetype`. Call it once `fingerprint` has read the package, which refuses one
        that isn't a zip or inflates past its limit.

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
                message = f"not a {self.extension}: its content types are {error}"
                raise AppFailed("refused", message) from None
        declared = (override.get("ContentType", "") for override in types.iter(TYPES))
        return next((self.main[found] for found in declared if found in self.main), None)

    def fingerprint(self, content: bytes, *, limit: int) -> str:
        """The digest of a package's parts, by name, without the parts each save stamps.

        Each part is hashed on its own, and the fingerprint is the digest of the parts' names
        and digests, so no two different files share one. Each part is read as it inflates, so
        a zip bomb is refused once it passes `limit`.

        Raises:
            AppFailed: `refused` if the bytes aren't a zip, or name a part twice, and
                `too_large` if its parts, inflated, pass `limit` bytes.
        """
        digest = hashlib.sha256()
        inflated = 0
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = archive.namelist()
                if len(set(names)) != len(names):
                    raise AppFailed("refused", f"not a {self.extension}: it names a part twice")
                for name in sorted(set(names) - self.stamped):
                    part = hashlib.sha256()
                    with archive.open(name) as stream:
                        while chunk := stream.read(CHUNK):
                            inflated += len(chunk)
                            if inflated > limit:
                                message = f"its parts inflate past {limit} bytes"
                                raise AppFailed("too_large", message)
                            part.update(chunk)
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
