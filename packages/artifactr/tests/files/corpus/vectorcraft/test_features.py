"""VectorCraft's corpus: what each feature's value means."""

from tests.files.corpus.vectorcraft.corpus import CORPUS
from tests.files.corpus.vectorcraft.features import READERS, read


def value(feature: str) -> object:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("shapes") == [
        ("box", (10.0, 10.0, 90.0, 50.0)),
        ("dot", (130.0, 30.0, 170.0, 70.0)),
        ("wedge", (100.0, 60.0, 180.0, 90.0)),
    ]
    assert value("transforms") == [("turned", (85.86, 50.0, 128.28, 92.43))]
    assert value("groups") == [("Back", ("sky",)), ("Front", ("house",)), ("house", ("wall",))]
    assert value("text") == [
        ("Hello", "Helvetica", 12.0, (10.0, 30.0)),
        ("World", "Helvetica", 18.0, (10.0, 60.0)),
    ]
    assert value("gradients") == [("fade", "linearGradient", ((0.0, "#ff0000"), (1.0, "#0000ff")))]


def test_a_saved_shape_is_read_as_its_source_is() -> None:
    """VectorCraft saves a rectangle as a path, and bakes its transform into the path."""
    saved = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">'
        b'<g id="Layer_1"><path id="turned" d="M100 50 L128.284 78.284 L114.142 92.426 '
        b'L85.858 64.142 Z" fill="#333333"/></g></svg>'
    )
    assert read("transforms", saved) == value("transforms")
    assert read("groups", saved) == []


def test_every_feature_has_a_reader() -> None:
    assert set(READERS) == set(CORPUS.makers)


def test_each_hostile_file_is_its_format_broken() -> None:
    assert b"<!ENTITY e9" in CORPUS.hostile_file("laughs")
    assert b"SYSTEM" in CORPUS.hostile_file("external")
    assert CORPUS.hostile_file("nested").count(b"<g>") == 100_000
    assert not CORPUS.hostile_file("unclosed").rstrip().endswith(b"</svg>")
