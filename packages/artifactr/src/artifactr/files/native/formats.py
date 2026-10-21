"""What an upload is, from its first bytes, never from what its client says, and what it is named.

An upload's `Content-Type` and its name are the client's to say, so neither picks the format: the
first bytes are matched against each format the native type holds, and the app's inspection, in
the worker, reads it after. The signatures only tell a zip from a PDF from a Photoshop file; they
never open a zip, which is the app's, so every format packaged in a zip matches any zip, and the
app tells them apart.
"""

import re
import unicodedata
from collections.abc import AsyncIterable, AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Final

from artifactr.files.manifest import (
    BLEND,
    DOCX,
    DWG,
    DXF,
    ECPROJ,
    FCPROJ,
    FCSTD,
    FIGCRAFT,
    IDML,
    PDF,
    PPTX,
    PSD,
    SCRAFT,
    SVG,
    XLSX,
)

HEAD: Final = 4096
"""How many of an upload's first bytes its format is told from."""

PROJECT: Final = 2 << 20
"""The most bytes a crafting app's JSON project holds, as its adapter reads it (`craft.project`)."""

NAME_LIMIT: Final = 200
"""The most characters a file's name keeps, with its extension."""

NAME_BYTES: Final = 255
"""The most bytes, in UTF-8, a file's name keeps: what most file systems take."""

RESERVED: Final = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"{d}{n}" for d in ("COM", "LPT") for n in range(1, 10))}
)
"""The names Windows reserves for devices, whatever their extension, which a name is kept from."""


@dataclass(frozen=True)
class Format:
    """A format an upload may be: its extension, and whether the first bytes are of it."""

    extension: str
    """The extension a file of it is named with, such as `.docx`."""
    matches: Callable[[bytes], bool]
    """Whether the first bytes, up to `HEAD`, may be a file of it."""
    most: int | None = None
    """The most bytes a file of it holds, if fewer than the store keeps: past them an upload is
    refused as it streams, rather than read whole only for the app to refuse it."""
    told: bool = True
    """Whether its first bytes tell it from every other format: not for one packaged in a zip,
    which an upload's app must then name, or the upload is refused."""


def _zip(head: bytes) -> bool:
    return head.startswith(b"PK\x03\x04")


def _text(head: bytes) -> str:
    """The first bytes as text, without a byte order mark or the whitespace before them."""
    return head.removeprefix(b"\xef\xbb\xbf").decode("utf-8", "replace").lstrip()


def _json(head: bytes) -> bool:
    """A JSON object, after any byte order mark or whitespace."""
    return _text(head).startswith("{")


def _svg(head: bytes) -> bool:
    """Markup, with an `<svg` element in its first bytes, after any declaration or comment."""
    text = _text(head)
    return text.startswith("<") and re.search(r"<svg[\s>]", text) is not None


def _dxf(head: bytes) -> bool:
    """A binary DXF's sentinel, or an ASCII DXF's first group: `0`, then `SECTION`."""
    binary = head.startswith(b"AutoCAD Binary DXF")
    return binary or re.match(r"0\s*\r?\n\s*SECTION\b", _text(head)) is not None


FORMATS: Final[Mapping[str, Format]] = {
    DOCX: Format(".docx", _zip, told=False),
    XLSX: Format(".xlsx", _zip, told=False),
    PPTX: Format(".pptx", _zip, told=False),
    IDML: Format(".idml", _zip, told=False),
    FIGCRAFT: Format(".figcraft", _zip, told=False),
    FCSTD: Format(".FCStd", _zip, told=False),
    PDF: Format(".pdf", lambda head: head.startswith(b"%PDF-")),
    PSD: Format(".psd", lambda head: head.startswith(b"8BPS")),
    DWG: Format(".dwg", lambda head: re.match(rb"AC10[0-3][0-9]", head) is not None),
    DXF: Format(".dxf", _dxf),
    SVG: Format(".svg", _svg),
    # The crafting apps' projects are JSON objects alike: the app tells them apart.
    FCPROJ: Format(".fcproj", _json, most=PROJECT, told=False),
    ECPROJ: Format(".ecproj", _json, most=PROJECT, told=False),
    SCRAFT: Format(".scraft", _json, most=PROJECT, told=False),
    # Blender's own header, or zstd's frame, which Blender compresses with: the app tells them.
    BLEND: Format(
        ".blend", lambda head: head.startswith((b"BLENDER", b"\x28\xb5\x2f\xfd")), told=False
    ),
}
"""Each native type's format, by its media type. An application with a native type of its own
gives [`NativeFiles`][artifactr.files.native.NativeFiles] these and its format's."""


async def sniffed(
    data: AsyncIterable[bytes], formats: Mapping[str, Format], allowed: frozenset[str]
) -> tuple[str | None, AsyncIterator[bytes]]:
    """The format, of those `allowed`, an upload's first bytes are; and the upload, whole.

    The first of the allowed formats, in their order, that the first bytes match is the
    upload's; None if none is, or the upload is empty.
    """
    stream = aiter(data)
    head = b""
    async for chunk in stream:
        head += chunk
        if len(head) >= HEAD:
            break
    known = [media_type for media_type in sorted(allowed) if media_type in formats]
    found = next((m for m in known if head and formats[m].matches(head[:HEAD])), None)
    return found, _resumed(head, stream)


async def _resumed(head: bytes, rest: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    if head:
        yield head
    async for chunk in rest:
        yield chunk


REFUSED: Final = frozenset('/\\:*?"<>|')
"""The characters a file system refuses in a name, beside every control and format character."""


def file_name(given: str, extension: str, formats: Mapping[str, Format]) -> str:
    """A file's name as kept: no path, no control characters, capped, and with its extension.

    What a client gives is the last part of any path, normalized (NFC), with every control or
    format character, such as a right-to-left override, and every one a file system refuses
    replaced by `_`; a name Windows reserves, such as `CON`, is prefixed with `_`. Its
    extension is the format's: one of another format's is replaced, and any other kept before
    it. An empty name is `file`. It is capped in characters and in UTF-8 bytes.
    """
    last = re.split(r"[/\\]", unicodedata.normalize("NFC", given))[-1]
    kept = (c if unicodedata.category(c)[0] != "C" and c not in REFUSED else "_" for c in last)
    name = "".join(kept).strip(" .")
    stem, dot, suffix = name.rpartition(".")
    known = {f.extension.lower() for f in formats.values()}
    if dot and f".{suffix.lower()}" in known:
        name = stem
    name = name.strip(" .") or "file"
    if name.partition(".")[0].upper() in RESERVED:
        name = f"_{name}"
    name = name[: NAME_LIMIT - len(extension)]
    while len((name + extension).encode()) > NAME_BYTES:
        name = name[:-1]
    return name + extension
