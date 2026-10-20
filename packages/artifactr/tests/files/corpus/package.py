"""What the zip packages' corpora share: a package written the same way every time, an image,
and the hostile files each format of them adds.

WordCraft's, GridCraft's and DeckCraft's files are Office Open XML packages, zips of XML parts:
each corpus writes its parts by hand, and this zips them with a fixed time on every entry, so the
same code makes the same bytes.
"""

import io
import struct
import zipfile
import zlib
from collections.abc import Mapping
from typing import Final
from xml.etree import ElementTree

TIME: Final = (2026, 10, 17, 0, 0, 0)
XML: Final = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
RELS: Final = "application/vnd.openxmlformats-package.relationships+xml"
PKG: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
REL: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
TYPES: Final = "http://schemas.openxmlformats.org/package/2006/content-types"


def zipped(files: Mapping[str, bytes | str]) -> bytes:
    """A zip of the files, in order, deflated, each at the same time."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            archive.writestr(zipfile.ZipInfo(name, TIME), data, zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def png(width: int, height: int) -> bytes:
    """A PNG of a gradient, so its bytes are an image's and not a blank's."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(
        b"\0" + b"".join(bytes((x * 255 // width, y * 255 // height, 128)) for x in range(width))
        for y in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def types(defaults: Mapping[str, str], overrides: Mapping[str, str]) -> str:
    """A package's content types: by extension, then by part."""
    return (
        f'{XML}<Types xmlns="{TYPES}">'
        + "".join(f'<Default Extension="{e}" ContentType="{t}"/>' for e, t in defaults.items())
        + "".join(f'<Override PartName="/{p}" ContentType="{t}"/>' for p, t in overrides.items())
        + "</Types>"
    )


def relationships(
    targets: Mapping[str, tuple[str, str]], external: Mapping[str, tuple[str, str]] | None = None
) -> str:
    """A part's relationships, `{id: (type, target)}`, each type after `.../relationships/`, and
    those whose targets are outside the package, such as a link's."""
    inside = (
        f'<Relationship Id="{rid}" Type="{REL}/{kind}" Target="{target}"/>'
        for rid, (kind, target) in targets.items()
    )
    outside = (
        f'<Relationship Id="{rid}" Type="{REL}/{kind}" Target="{target}" TargetMode="External"/>'
        for rid, (kind, target) in (external or {}).items()
    )
    return f'{XML}<Relationships xmlns="{PKG}">{"".join([*inside, *outside])}</Relationships>'


def parts(content: bytes, stamped: frozenset[str] = frozenset()) -> dict[str, bytes]:
    """A package's parts, without those each save stamps."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist() if name not in stamped}


def canonical(content: bytes) -> dict[str, bytes]:
    """A package's parts, each XML part in its canonical form (C14N 2.0), as an app that writes
    the same XML in more than one way is held to it."""
    return {
        name: ElementTree.canonicalize(part.decode()).encode()
        if name.endswith((".xml", ".rels"))
        else part
        for name, part in parts(content).items()
    }


def bomb(content: bytes, main: str) -> bytes:
    """The package with its main part inflating to 300 MiB from 300 KiB, a comment after its
    XML declaration, written a MiB at a time."""
    made = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(content)) as source,
        zipfile.ZipFile(made, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        for name in source.namelist():
            part = source.read(name)
            if name != main:
                archive.writestr(name, part)
                continue
            head, _, tail = part.partition(b"?>")
            with archive.open(name, "w", force_zip64=True) as stream:
                stream.write(head + b"?><!--")
                for _ in range(300):
                    stream.write(b" " * (1 << 20))
                stream.write(b"-->" + tail)
    return made.getvalue()


def untyped(content: bytes) -> bytes:
    """The package with content types that aren't XML."""
    return zipped(
        {
            name: b"<Types" if name == "[Content_Types].xml" else part
            for name, part in parts(content).items()
        }
    )
