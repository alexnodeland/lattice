"""PdfCraft's corpus: what each feature's value means."""

from tests.files.corpus.pdfcraft.corpus import CORPUS
from tests.files.corpus.pdfcraft.features import READERS, Value, kept, read


def value(feature: str) -> Value:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("text") == [(1, "The parties agree to the terms."), (1, "Signed in May.")]
    assert value("pages") == [
        ((0.0, 0.0, 612.0, 792.0), 0),
        ((0.0, 0.0, 792.0, 612.0), 0),
        ((0.0, 0.0, 612.0, 792.0), 90),
    ]
    assert ("Keywords", b"revenue, costs") in value("metadata")
    assert value("bookmarks") == [(0, b"Introduction", 1), (0, b"Results", 2), (1, b"By region", 2)]
    assert value("comments") == [(1, b"Ada", b"Check this figure.", (72.0, 700.0, 92.0, 720.0))]
    assert [goes for _, _, goes in value("links")] == [b"https://example.com/", 2]
    assert value("forms") == [(b"name", "Tx", b"Ada Lovelace"), (b"agreed", "Btn", "Yes")]
    assert value("page_labels") == [(0, "r", 1), (1, "D", 1)]
    assert [image[1:3] for image in value("images")] == [(16, 8)]


def test_what_two_saves_keep_leaves_out_the_stamp() -> None:
    source = CORPUS.source("metadata")
    stamped = source.replace(
        b"/Title (Annual report)", b"/ModDate (D:20260101)/Title (Annual report)"
    )
    assert kept(stamped) == kept(source)


def test_every_feature_has_a_reader() -> None:
    assert set(READERS) == set(CORPUS.makers)
