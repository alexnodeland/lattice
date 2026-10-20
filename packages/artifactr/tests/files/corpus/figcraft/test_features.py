"""FigCraft's corpus: what each feature's value means."""

from tests.files.corpus.figcraft.corpus import CORPUS
from tests.files.corpus.figcraft.features import READERS, read


def value(feature: str) -> object:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("pages") == [("Cover", ("On the cover",)), ("Details", ("On the details",))]
    assert value("groups") == [("Pair", ("Left", "Right"))]
    assert value("components") == [
        ("component", "Button", (0.0, 0.0, 40.0, 20.0), None),
        ("instance", "Button", (100.0, 0.0, 40.0, 20.0), "Button"),
    ]
    assert value("auto_layout") == [("Stack", "vertical", 12.0, (8.0, 8.0, 8.0, 8.0))]
    assert value("variables") == [("Tokens", "gap", "number", (("Base", 8.0),))]
    assert value("styles") == [
        ("Brand/Red", "paint", ((1.0, 0.0, 0.0, 1.0),)),
        ("Box", "fill", "Brand/Red"),
    ]
    assert value("comments") == [("Ada", "Check the spacing", False, 5.0, 5.0)]


def test_every_feature_has_a_reader() -> None:
    assert set(READERS) == set(CORPUS.makers)


def test_each_hostile_file_says_it_is_a_figcraft_and_is_broken() -> None:
    for name in ("not_json", "future_version", "unknown_layer"):
        assert b"document.json" in CORPUS.hostile_file(name)
