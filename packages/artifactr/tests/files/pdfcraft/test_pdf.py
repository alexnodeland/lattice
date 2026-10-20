"""What the adapter reads from a `.pdf` itself: the fingerprint, the format, and the outline."""

import pytest

from artifactr.files.app import AppFailed
from artifactr.files.manifest import OUTLINE_LIMIT, PDF
from artifactr.files.pdfcraft import fingerprint, media_type, outline
from artifactr.files.pdfcraft.pdf import Bookmark
from tests.files.corpus.pdfcraft.make import FONT, page, pdf, stream, words

LIMIT = 1 << 20


def saved(info: str, *, shown: str = "Report", where: int = 0, more: tuple[str, ...] = ()) -> bytes:
    """A document as PdfCraft saves one: its information dictionary packed in an object stream,
    and a cross-reference stream, which here says nothing but where `where` puts it."""
    packed = f"<< /Title (Report) {info}>>".encode()
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        FONT,
        page("5 0 R"),
        words(shown),
        stream(b"6 0 " + packed, "/Type /ObjStm /N 1 /First 4 "),
        stream(where.to_bytes(4, "big"), "/Type /XRef /W [1 2 1] "),
        *more,
    ]
    return pdf(objects, "/Info 6 0 R ")


def test_the_date_each_save_stamps_and_where_objects_lie_leave_it_alone() -> None:
    once = saved("/ModDate (D:20261020160617Z) ")
    twice = saved("/ModDate (D:20261020160618Z) ", where=7)
    assert once != twice
    assert fingerprint(once, limit=LIMIT) == fingerprint(twice, limit=LIMIT)


@pytest.mark.parametrize(
    "changed",
    [saved("/Author (Ada) "), saved("", shown="Another report"), saved("", more=("<< >>",))],
    ids=["packed", "content", "after"],
)
def test_anything_else_changes_it(changed: bytes) -> None:
    assert fingerprint(saved(""), limit=LIMIT) != fingerprint(changed, limit=LIMIT)


def test_a_stream_given_its_length_by_reference_is_read_as_written() -> None:
    def where(at: bytes) -> bytes:
        xref = "<< /Type /XRef /Length 6 0 R >>\nstream\n" + at.decode() + "\nendstream"
        return pdf(["<< /Type /Catalog >>", xref])

    assert fingerprint(where(b"\x01"), limit=LIMIT) != fingerprint(where(b"\x02"), limit=LIMIT)


def test_object_streams_that_inflate_past_the_limit_are_too_large() -> None:
    bomb = stream(b" " * (LIMIT + 1), "/Type /ObjStm /N 1 /First 4 ")
    with pytest.raises(AppFailed, match="inflate past") as large:
        fingerprint(pdf(["<< /Type /Catalog >>", bomb]), limit=LIMIT)
    assert large.value.failure == "too_large"


def test_an_object_stream_that_isnt_deflated_whole_is_refused() -> None:
    garbled = "<< /Type /ObjStm /Filter /FlateDecode /Length 4 >>\nstream\nnope\nendstream"
    with pytest.raises(AppFailed, match=r"not a \.pdf: an object stream is") as refused:
        fingerprint(pdf(["<< /Type /Catalog >>", garbled]), limit=LIMIT)
    assert refused.value.failure == "refused"


def test_a_file_says_it_is_a_pdf_by_its_header() -> None:
    assert media_type(saved("")) == PDF
    assert media_type(b"\0" * 10 + b"%PDF-1.4") == PDF
    assert media_type(b"PK\x03\x04") is None


def test_the_outline_is_the_bookmarks_indented_under_their_parents() -> None:
    bookmarks = [
        Bookmark(
            title="Start", children=[Bookmark(title="Detail", children=[Bookmark(title="Deep")])]
        ),
        Bookmark(title="End"),
    ]
    assert outline(bookmarks) == "Start\n  Detail\n    Deep\nEnd"
    assert len(outline([Bookmark(title="x" * 50)] * 200)) == OUTLINE_LIMIT
