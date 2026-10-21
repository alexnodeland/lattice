"""EffectCraft's corpus: what each feature's value means."""

from tests.files.corpus.effectcraft.corpus import CORPUS
from tests.files.corpus.effectcraft.features import READERS, read
from tests.files.corpus.effectcraft.make import MADE

SECOND = 254_016_000_000


def value(feature: str) -> object:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("compositions") == [
        ("Main", 64, 36, 24, 2 * SECOND),
        ("Square", 48, 48, 30, SECOND),
    ]
    assert value("folders") == [
        ("Main", "Comp", "Inner"),
        ("Parts", "Folder", None),
        ("Inner", "Folder", "Parts"),
    ]
    assert value("text") == [
        ("Body", "Second line", "Inter", 12.0),
        ("Hello", "Hello", "Inter", 24.0),
    ]
    assert value("keyframes") == [
        ("Red", "layer/transform/position", [(0, (0.0, 0.0, 0.0)), (SECOND, (32.0, 18.0, 0.0))])
    ]
    assert value("effects") == [("Red", ["ec.blur.gaussian"])]
    assert value("expressions") == [("Red", "layer/transform/rotation", "time * 90", True)]
    assert value("markers") == [
        ("Main", SECOND // 2, "Beat"),
        ("Main", 3 * SECOND // 2, "Cut here"),
    ]
    assert value("parenting") == [("Rig", None), ("Red", "Rig")]
    assert value("precomps") == [
        ("Main", "Inside", "Comp", "Inside"),
        ("Inside", "Red", "Solid", "Red"),
    ]


def test_every_feature_has_a_reader_and_a_script() -> None:
    assert set(READERS) == set(CORPUS.makers) == set(MADE.scripts)


def test_each_hostile_file_says_which_release_saved_it() -> None:
    for name in CORPUS.hostile:
        assert b'"savedBy": "0.11.1"' in CORPUS.hostile_file(name), name
