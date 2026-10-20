"""What the adapter reads from a `.pptx` itself: the fingerprint, the format, outline and text."""

from collections.abc import Callable

import pytest

from artifactr.files.app import AppFailed
from artifactr.files.craft import package as craft_package
from artifactr.files.deckcraft import fingerprint, media_type, outline, text
from artifactr.files.deckcraft.pptx import Shape, Slide, Table
from artifactr.files.manifest import OUTLINE_LIMIT, PPTX
from tests.files.corpus import package
from tests.files.corpus.deckcraft.corpus import CORPUS

LIMIT = 1 << 20
SLIDE = "ppt/slides/slide1.xml"


def slide(xml: str) -> bytes:
    return package.zipped({SLIDE: xml, "ppt/media/image1.png": b"\x89PNG"})


def test_xml_written_in_another_way_is_the_same_fingerprint() -> None:
    one = slide('<p:sld xmlns:a="urn:a" xmlns:p="urn:p"><a:p/></p:sld>')
    other = slide('<p:sld xmlns:p="urn:p"><a:p xmlns:a="urn:a"></a:p></p:sld>')
    changed = slide('<p:sld xmlns:a="urn:a" xmlns:p="urn:p"><a:p>Hi</a:p></p:sld>')
    assert fingerprint(one, limit=LIMIT) == fingerprint(other, limit=LIMIT)
    assert fingerprint(one, limit=LIMIT) != fingerprint(changed, limit=LIMIT)


def test_an_xml_part_that_isnt_xml_is_refused() -> None:
    with pytest.raises(AppFailed, match=rf"not a \.pptx: {SLIDE} is") as refused:
        fingerprint(slide("<p:sld"), limit=LIMIT)
    assert refused.value.failure == "refused"


def test_a_package_says_its_format_by_its_main_part() -> None:
    assert media_type(CORPUS.source("text")) == PPTX


def test_the_outline_is_each_titled_slide_by_its_number() -> None:
    slides = [Slide(title="Opening"), Slide(), Slide(title="Closing")]
    assert outline(slides) == "1. Opening\n3. Closing"
    assert len(outline([Slide(title="x" * 50)] * 200)) == OUTLINE_LIMIT


def test_the_text_is_each_slides_shapes_tables_and_notes() -> None:
    table = Table(cells=[["Region", "Revenue"], ["North", "120"]])
    slides = [
        Slide(shapes=[Shape(text="Results"), Shape(table=table), Shape()], notes="Say hi"),
        Slide(shapes=[Shape(text="Thanks")]),
    ]
    assert text(slides) == "Results\nRegion\tRevenue\nNorth\t120\nSay hi\n\nThanks"


@pytest.mark.parametrize(
    ("made", "failure", "found"),
    [
        (lambda: package.nested(CORPUS.source("text"), SLIDE), "refused", "nests deeper than 256"),
        (
            lambda: package.flat(CORPUS.source("text"), SLIDE),
            "too_large",
            "more than 1000 elements",
        ),
        (
            lambda: package.zipped({SLIDE: b"<a>" + b" " * (16 << 20) + b"</a>"}),
            "too_large",
            "larger than 16777216 bytes",
        ),
    ],
    ids=["nested", "flat", "large"],
)
def test_xml_read_in_its_canonical_form_is_bounded(
    made: Callable[[], bytes], failure: str, found: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The live hostile files hold the time it takes; here, fewer elements are enough.
    monkeypatch.setattr(craft_package, "ELEMENTS", 1000)
    with pytest.raises(AppFailed, match=found) as bounded:
        fingerprint(made(), limit=1 << 28)
    assert bounded.value.failure == failure


def test_a_mimetype_that_claims_a_presentation_is_no_format() -> None:
    assert media_type(package.spoofed(CORPUS.source("text"), PPTX)) is None
