"""What the adapter reads from a `.docx` itself: the fingerprint, and the outline."""

import io
import zipfile

import pytest
from hypothesis import given
from hypothesis import strategies as st

from artifactr.files.app import AppFailed
from artifactr.files.manifest import OUTLINE_LIMIT
from artifactr.files.wordcraft import STAMPED, fingerprint, outline
from artifactr.files.wordcraft.docx import Block

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


def test_a_parts_name_and_its_bytes_are_told_apart() -> None:
    assert fingerprint(docx({"ab": b"c"}), limit=LIMIT) != fingerprint(
        docx({"a": b"bc"}), limit=LIMIT
    )


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
