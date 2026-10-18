"""What the adapter reads from a `.docx` itself: the fingerprint, the format, and the outline."""

import io
import warnings
import zipfile
from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st

from artifactr.files.app import AppFailed
from artifactr.files.manifest import DOCX, OUTLINE_LIMIT
from artifactr.files.wordcraft import STAMPED, fingerprint, media_type, outline
from artifactr.files.wordcraft.docx import Block
from tests.files.corpus.wordcraft.corpus import CORPUS

LIMIT = 1 << 20
NAMES = st.sampled_from(["word/document.xml", "word/styles.xml", "[Content_Types].xml", "a"])
PARTS = st.dictionaries(NAMES, st.binary(max_size=64), min_size=1)


def docx(parts: dict[str, bytes], *, compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return buffer.getvalue()


@given(parts=PARTS, stamps=st.lists(st.binary(max_size=32), min_size=2, max_size=2))
def test_what_each_save_stamps_and_the_parts_order_leave_it_alone(
    parts: dict[str, bytes], stamps: list[bytes]
) -> None:
    (stamped,) = STAMPED
    first = docx({**parts, stamped: stamps[0]})
    second = docx({stamped: stamps[1], **dict(reversed(parts.items()))}, compression=0)
    assert fingerprint(first, limit=LIMIT) == fingerprint(second, limit=LIMIT)


@given(parts=PARTS, name=NAMES, data=st.binary(max_size=64))
def test_any_other_part_changes_it(parts: dict[str, bytes], name: str, data: bytes) -> None:
    changed = {**parts, name: data}
    same = parts.get(name) == data
    assert (
        fingerprint(docx(parts), limit=LIMIT) == fingerprint(docx(changed), limit=LIMIT)
    ) == same


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ({"ab": b"c"}, {"a": b"bc"}),
        ({"a": b"P\x001:bQ"}, {"a": b"P", "b": b"Q"}),
    ],
)
def test_parts_names_and_bytes_are_told_apart(
    one: dict[str, bytes], other: dict[str, bytes]
) -> None:
    assert fingerprint(docx(one), limit=LIMIT) != fingerprint(docx(other), limit=LIMIT)


def corrupt() -> bytes:
    """A zip whose part's deflate stream is garbage."""
    content = bytearray(docx({"word/document.xml": b"<w:document/>" * 50}))
    start = content.index(b"word/document.xml") + len("word/document.xml")
    content[start : start + 20] = b"\xff" * 20
    return bytes(content)


def encrypted() -> bytes:
    """A zip whose part says it is encrypted."""
    content = bytearray(docx({"word/document.xml": b"<w:document/>"}))
    for header in (b"PK\x03\x04", b"PK\x01\x02"):
        at = content.index(header) + (6 if header == b"PK\x03\x04" else 8)
        content[at] |= 1
    return bytes(content)


def duplicated() -> bytes:
    buffer = io.BytesIO()
    with warnings.catch_warnings(action="ignore"), zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", b"one")
        archive.writestr("word/document.xml", b"two")
    return buffer.getvalue()


@pytest.mark.parametrize("made", [corrupt, encrypted, duplicated])
def test_a_zip_that_isnt_whole_or_plain_is_refused(made: Callable[[], bytes]) -> None:
    with pytest.raises(AppFailed, match=r"not a \.docx") as refused:
        fingerprint(made(), limit=LIMIT)
    assert refused.value.failure == "refused"


def test_bytes_that_arent_a_zip_are_refused() -> None:
    with pytest.raises(AppFailed, match=r"not a \.docx") as refused:
        fingerprint(b"PK not a zip", limit=LIMIT)
    assert refused.value.failure == "refused"


def test_parts_that_inflate_past_the_limit_are_too_large() -> None:
    bomb = docx({"word/document.xml": b"\0" * (LIMIT + 1)})
    assert len(bomb) < LIMIT // 100
    with pytest.raises(AppFailed, match="inflate past") as large:
        fingerprint(bomb, limit=LIMIT)
    assert large.value.failure == "too_large"


def test_the_outline_is_the_headings_indented_by_level() -> None:
    blocks = [
        Block(text="Contract", style="Title"),
        Block(text="Terms", style="heading 1"),
        Block(text="Pay within thirty days", style="Normal"),
        Block(text="Late fees\nand interest", style="Heading2"),
        Block(text="Deep", style="Heading 12"),
        Block(text="Shallow", style="Heading 0"),
        Block(text="Not one", style="Heading One"),
        Block(text="Nor this", style="Subtitle"),
        Block(text="   ", style="Heading 1"),
    ]
    expected = "Contract\nTerms\n  Late fees\n" + "  " * 8 + "Deep\nShallow"
    assert outline(blocks) == expected


def test_without_headings_the_outline_is_each_blocks_first_line() -> None:
    blocks = [Block(text="One\nmore"), Block(), Block(text="Two", style=None)]
    assert outline(blocks) == "One\nTwo"


def test_the_outline_keeps_to_its_limit() -> None:
    assert len(outline([Block(text="x" * 50, style="Heading 1")] * 200)) == OUTLINE_LIMIT


def test_a_package_says_its_format_by_its_main_part_or_its_mimetype() -> None:
    assert media_type(CORPUS.source("text")) == DOCX
    types = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/docProps/core.xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"/></Types>'
    )
    assert media_type(docx({"[Content_Types].xml": types.encode()})) == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.template"
    )
    assert media_type(docx({"mimetype": b"application/vnd.oasis.opendocument.text"})) == (
        "application/vnd.oasis.opendocument.text"
    )
    assert media_type(docx({"word/document.xml": b"<w/>"})) is None
    assert media_type(docx({"[Content_Types].xml": b"<Types/>"})) is None


def test_content_types_that_arent_xml_are_refused() -> None:
    with pytest.raises(AppFailed, match="its content types are") as refused:
        media_type(docx({"[Content_Types].xml": b"<Types"}))
    assert refused.value.failure == "refused"
