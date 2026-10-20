"""GridCraft's corpus: what each feature's value means."""

from tests.files.corpus.gridcraft.corpus import CORPUS
from tests.files.corpus.gridcraft.features import READERS, Value, read


def value(feature: str) -> Value:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("values")[:3] == [
        ("Fees", "A1", "Item"),
        ("Fees", "B1", "Fee"),
        ("Fees", "C1", "Paid"),
    ]
    assert ("Fees", "B3", 20.5) in value("values")
    assert ("Fees", "C2", True) in value("values")
    assert value("formulas") == [
        ("Sums", "B1", "A1*2"),
        ("Sums", "B2", 'IF(A2>10,"high","low")'),
        ("Sums", "A3", "SUM(A1:A2)"),
    ]
    assert value("number_formats") == [
        ("Formats", "A1", '#,##0.00 "EUR"'),
        ("Formats", "A2", "0.00%"),
        ("Formats", "A3", "m/d/yyyy"),
    ]
    assert value("fonts_and_fills") == [
        ("Styled", "A1", True, False, None, None),
        ("Styled", "A2", False, True, "FFFF0000", "FFFFFF00"),
        ("Styled", "A3", False, False, None, None),
    ]
    assert value("sheets") == [("First", "visible"), ("Second", "visible"), ("Hidden", "hidden")]
    assert value("sizes") == [
        ("col", "Sized", "1", "1", 30.0),
        ("col", "Sized", "3", "4", 5.0),
        ("row", "Sized", "2", 40.0),
    ]
    assert value("comments") == [("Noted", "B2", "Ada", "Check this fee.")]
    assert value("data_validation") == [
        ("Checked", "A2:A9", "list", "between", ('"Yes,No"',)),
        ("Checked", "B2:B9", "whole", "between", ("1", "10")),
    ]
    assert value("tables") == [("Tabled", "Fees", "A1:B3", ("Item", "Fee"))]
    assert value("hyperlinks") == [
        ("Linked", "A1", "https://example.com/"),
        ("Linked", "A2", "Linked!B5"),
    ]


def test_every_feature_has_a_reader() -> None:
    assert set(READERS) == set(CORPUS.makers)
