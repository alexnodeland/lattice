"""FilmCraft's corpus: what each feature's value means."""

from tests.files.corpus.filmcraft.corpus import CORPUS
from tests.files.corpus.filmcraft.features import READERS, read
from tests.files.corpus.filmcraft.make import MADE

SECOND = 254_016_000_000


def value(feature: str) -> object:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("sequences") == [("Main", 64, 36, 24), ("Square", 48, 48, 30)]
    assert value("bins") == [(0, "Selects"), (1, "Inner"), (2, "Color Matte")]
    assert value("clips") == [
        ("Video 1", "Color Matte", 0, 2 * SECOND),
        ("Video 1", "Color Matte", 2 * SECOND, 2 * SECOND),
    ]
    assert value("keyframes") == [
        ("opacity", "opacity", [(0, 0.0, "Linear"), (SECOND, 100.0, "Linear")])
    ]
    assert value("titles") == [("Hello", "Hello", "Inter", 24.0, (1.0, 0.8, 0.0, 1.0))]
    assert value("captions") == [
        ("Subtitle", "Subtitle", "First words", 0, SECOND),
        ("Subtitle", "Subtitle", "Second words", SECOND, SECOND),
    ]
    assert value("markers") == [
        ("Comment", "Beat", "Cut here", SECOND),
        ("Chapter", "Part two", "", 2 * SECOND),
    ]
    assert value("color") == [("Color Matte", "", "builtin:look-teal-orange")]


def test_every_feature_has_a_reader_and_a_script() -> None:
    assert set(READERS) == set(CORPUS.makers) == set(MADE.scripts)


def test_each_hostile_file_says_it_is_a_fcproj() -> None:
    for name in CORPUS.hostile:
        assert b'"format": "filmcraft.project"' in CORPUS.hostile_file(name), name
