"""The corpus: one file per feature, as `make.py` makes it, each holding its feature."""

import pytest

from tests.files.corpus.features import READERS, read
from tests.files.corpus.make import FEATURES, HERE


def test_the_corpus_is_what_make_makes() -> None:
    assert sorted(p.name for p in HERE.iterdir()) == sorted(f"{f}.docx" for f in FEATURES)
    for feature, make in FEATURES.items():
        assert (HERE / f"{feature}.docx").read_bytes() == make(), (
            f"{feature}.docx drifted: run python -m tests.files.corpus.make"
        )


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_each_file_holds_its_feature(feature: str) -> None:
    assert read(feature, (HERE / f"{feature}.docx").read_bytes())
    assert set(READERS) == set(FEATURES)


def test_a_features_value_is_what_it_means() -> None:
    def value(feature: str) -> object:
        return read(feature, (HERE / f"{feature}.docx").read_bytes())

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
