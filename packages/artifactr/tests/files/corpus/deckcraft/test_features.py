"""DeckCraft's corpus: what each feature's value means."""

from tests.files.corpus.deckcraft.corpus import CORPUS
from tests.files.corpus.deckcraft.features import READERS, Value, read


def value(feature: str) -> Value:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("text") == [
        (1, "title", "Results"),
        (1, "body", "Revenue grew in every region."),
        (1, "body", "Costs held flat."),
    ]
    assert value("slides") == [("Opening", True), ("Backup", False), ("Closing", True)]
    assert value("text_formatting")[0] == ("bold", True, False, "none", None, None)
    assert value("text_formatting")[-1] == ("red", False, False, "none", None, "FF0000")
    assert value("bullets") == [(0, "First"), (1, "Nested"), (2, "Deeper"), (0, "Second")]
    assert value("notes") == [(1, "Welcome everyone, then the numbers.")]
    assert value("tables") == [(("Region", "Revenue"), ("North", "120"), ("South", "95"))]
    assert value("images")[0][1:] == ((100, 100, 200, 150), "A gradient")
    assert value("shapes") == [
        ("ellipse", "2563EB", (100, 100, 120, 120)),
        ("rightArrow", "16A34A", (300, 140, 200, 60)),
    ]
    assert value("transitions") == [(1, ("fade",), "slow")]
    assert value("hyperlinks") == [("The site", "https://example.com/")]
    assert value("slide_size") == [(720, 540)]
    assert value("comments") == [(1, "Ada", "Check these numbers.")]


def test_every_feature_has_a_reader() -> None:
    assert set(READERS) == set(CORPUS.makers)
