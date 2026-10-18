"""WordCraft's corpus: what each feature's value means."""

from tests.files.corpus.wordcraft.corpus import CORPUS
from tests.files.corpus.wordcraft.features import READERS, read


def value(feature: str) -> object:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("styles") == [
        ("title", "Contract"),
        ("heading 1", "Terms"),
        ("normal", "Pay within thirty days."),
    ]
    assert value("lists") == [
        ("decimal", 0, "First"),
        ("lowerLetter", 1, "Nested"),
        ("decimal", 0, "Second"),
        ("bullet", 0, "Dot"),
    ]
    assert value("comments") == [("Ada", "Check the dates.", "Due on the first of May.")]
    assert value("tracked_changes") == [("del", "Ada", "100"), ("ins", "Ada", "120")]
    assert value("headers_and_footers") == [
        ("footer", "default", "Page footer"),
        ("header", "default", "Confidential"),
    ]
    assert value("footnotes") == [("As amended in 2025.",)]
    assert value("sections") == [
        (("12240", "15840", None), ("1440", "1440", "1440", "1440"), "1"),
        (("15840", "12240", "landscape"), ("720", "720", "720", "720"), "2"),
    ]


def test_every_feature_has_a_reader() -> None:
    assert set(READERS) == set(CORPUS.makers)
