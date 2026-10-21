"""What an upload is told to be by its first bytes, and the name it is kept under."""

from collections.abc import AsyncIterator

import pytest

from artifactr.files.manifest import (
    DOCX,
    DWG,
    DXF,
    FCSTD,
    FIGCRAFT,
    IDML,
    PDF,
    PPTX,
    PSD,
    SVG,
    XLSX,
    Drawing,
    VectorImage,
)
from artifactr.files.native import FORMATS
from artifactr.files.native.formats import HEAD, NAME_LIMIT, file_name, sniffed

ZIP = b"PK\x03\x04\x14\x00\x00\x00"


async def chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def joined(stream: AsyncIterator[bytes]) -> bytes:
    return b"".join([chunk async for chunk in stream])


@pytest.mark.parametrize(
    ("media_type", "head"),
    [
        (DOCX, ZIP),
        (XLSX, ZIP),
        (PPTX, ZIP),
        (IDML, ZIP),
        (FIGCRAFT, ZIP),
        (FCSTD, ZIP),
        (PDF, b"%PDF-1.7\n"),
        (PSD, b"8BPS\x00\x01"),
        (DWG, b"AC1032\x00"),
        (DXF, b"  0\r\nSECTION\r\n  2\r\nHEADER"),
        (DXF, b"AutoCAD Binary DXF\r\n\x1a\x00"),
        (SVG, b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
        (SVG, b'\xef\xbb\xbf<?xml version="1.0"?>\n<!-- drawn -->\n<svg>'),
    ],
)
def test_each_format_is_told_by_its_first_bytes(media_type: str, head: bytes) -> None:
    assert FORMATS[media_type].matches(head)


@pytest.mark.parametrize(
    ("media_type", "head"),
    [
        (DOCX, b"%PDF-1.7"),
        (PDF, b"MZ\x90\x00"),
        (PSD, ZIP),
        (DWG, b"AC2000"),
        (DXF, b"SECTION"),
        (SVG, b"<html><body>no image here</body></html>"),
        (SVG, b"#!/bin/sh\n<svg>"),
    ],
)
def test_no_format_is_told_by_anothers_bytes(media_type: str, head: bytes) -> None:
    assert not FORMATS[media_type].matches(head)


async def test_the_format_is_the_first_of_the_types_the_head_is() -> None:
    found, stream = await sniffed(chunks(b"AC1", b"032", b"rest"), FORMATS, Drawing.formats)
    assert found == DWG
    assert await joined(stream) == b"AC1032rest", "the upload, whole"
    found, _ = await sniffed(chunks(b"<svg/>"), FORMATS, Drawing.formats)
    assert found is None, "of no format the type holds"


async def test_the_head_is_read_up_to_its_limit_and_no_further() -> None:
    read: list[int] = []

    async def counted() -> AsyncIterator[bytes]:
        for i in range(4):
            read.append(i)
            yield b"<" + b" " * (HEAD // 2)

    found, stream = await sniffed(counted(), FORMATS, VectorImage.formats)
    assert (found, read) == (None, [0, 1]), "no <svg in the head, and two chunks were read"
    assert len(await joined(stream)) == 4 * (HEAD // 2 + 1)


async def test_an_empty_upload_is_of_no_format() -> None:
    found, stream = await sniffed(chunks(), FORMATS, frozenset({DOCX}))
    assert (found, await joined(stream)) == (None, b"")


async def test_a_format_no_table_knows_is_never_found() -> None:
    found, _ = await sniffed(chunks(ZIP), FORMATS, frozenset({"application/x-unknown"}))
    assert found is None


@pytest.mark.parametrize(
    ("given", "kept"),
    [
        ("contract.docx", "contract.docx"),
        ("Contract.DOCX", "Contract.docx"),
        ("../../etc/passwd", "passwd.docx"),
        ("C:\\Users\\eve\\terms.pdf", "terms.docx"),
        ("re\x00po\x1brt.v2", "re_po_rt.v2.docx"),
        ("invoice\u202excod.docx", "invoice_xcod.docx"),
        ("a<b>c:d|e?.docx", "a_b_c_d_e_.docx"),
        ("  . ", "file.docx"),
        ("/", "file.docx"),
        ("e\u0301te\u0301.docx", "\u00e9t\u00e9.docx"),
    ],
)
def test_a_name_keeps_no_path_or_control_and_takes_the_formats_extension(
    given: str, kept: str
) -> None:
    assert file_name(given, ".docx", FORMATS) == kept


def test_a_name_is_capped_with_its_extension() -> None:
    kept = file_name("x" * 1000, ".FCStd", FORMATS)
    assert len(kept) == NAME_LIMIT
    assert kept.endswith("x.FCStd")
