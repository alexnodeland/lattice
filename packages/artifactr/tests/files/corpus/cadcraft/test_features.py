"""CADCraft's corpus: what each feature's value means."""

from tests.files.corpus.cadcraft.corpus import CORPUS
from tests.files.corpus.cadcraft.features import READERS, read


def value(feature: str) -> object:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("layers") == [("Walls", 1, "CONTINUOUS"), ("Doors", 3, "CONTINUOUS")]
    assert value("blocks") == [
        ("Door", (20.0, 0.0), 0.0, ("LINE", "ARC")),
        ("Door", (40.0, 0.0), 90.0, ("LINE", "ARC")),
    ]
    assert value("polylines") == [(1, [(10.0, 10.0), (60.0, 10.0), (60.0, 40.0), (10.0, 40.0)])]
    assert value("text") == [
        ("TEXT", "Kitchen", (5.0, 5.0), 2.5),
        ("MTEXT", "Two\\Plines", (5.0, 20.0), 2.5),
    ]
    assert value("units") == [("4",)]


def test_every_feature_has_a_reader() -> None:
    assert set(READERS) == set(CORPUS.makers)


def test_each_hostile_file_is_its_format_broken() -> None:
    assert CORPUS.hostile_file("unread_dwg").startswith(b"AC1032")
    assert b"abc\n0.0" in CORPUS.hostile_file("bad_group")
