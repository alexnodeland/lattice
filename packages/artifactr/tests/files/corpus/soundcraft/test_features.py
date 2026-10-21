"""SoundCraft's corpus: what each feature's value means."""

from tests.files.corpus.soundcraft.corpus import CORPUS
from tests.files.corpus.soundcraft.features import READERS, read
from tests.files.corpus.soundcraft.make import MADE


def value(feature: str) -> object:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("tracks") == [
        ("Keys", "Instrument", "subtractive_synth"),
        ("Drums", "Instrument", "drum_synth"),
        ("Room", "Aux", None),
    ]
    assert value("midi") == [("Keys", "Keys", 0, 96_000, [(60, 100, 0, 480), (64, 80, 480, 480)])]
    assert value("mixer") == [("Keys", -6.0, (-0.5, 1.0), True)]
    assert value("sends") == [("Keys", 0, "Verb", -3.0)]
    assert value("automation") == [("Keys", "Volume", [(0, -12.0), (48_000, 0.0)])]
    assert value("markers") == [
        ("Verse", "Marker", 48_000, 48_000),
        ("Chorus", "Marker", 96_000, 96_000),
    ]
    assert value("tempo_and_meter") == [
        ("tempo", 0, 96.0),
        ("meter", 0, 3, 4),
        ("key", 0, "D minor"),
    ]
    assert value("comments") == [("Keys", "Play it softly")]


def test_every_feature_has_a_reader_and_a_script() -> None:
    assert set(READERS) == set(CORPUS.makers) == set(MADE.scripts)


def test_each_hostile_file_says_its_version() -> None:
    for name in CORPUS.hostile:
        assert b'"format_version": ' in CORPUS.hostile_file(name), name
