"""Blender's corpus: what each feature's value means, and what each hostile file is."""

from artifactr.files.blender.document import HEADER, read
from tests.files.corpus.blender.corpus import CORPUS, HOSTILE_FOLDER
from tests.files.corpus.blender.features import READERS, Value
from tests.files.corpus.blender.features import read as value_of


def value(feature: str) -> Value:
    return value_of(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("transforms") == [("Cube", (1.0, 2.0, 3.0), (0.0, 0.0, 28.648), (2.0, 1.0, 0.5))]
    assert value("materials") == [("Red", [0.8, 0.1, 0.1], 0.5, 0.25)]
    assert ("Sphere", 482, 512) in value("primitives")
    assert ("SubsurfModifierData", "Subdivision", 1, 2) in value("modifiers")
    assert ("Sun", 1, [1.0, 0.9, 0.8], 2.0) in value("camera_light")
    assert ("Camera", 35.0) in value("camera_light")
    assert value("collections") == [
        ("Scene Collection", ("Props",), ()),
        ("Props", ("Small",), ()),
        ("Small", (), ("Cube",)),
    ]
    assert value("render_settings") == [("Scene", 640, 360, "CYCLES")]


def test_every_feature_has_a_reader_and_is_made_by_blender() -> None:
    assert set(READERS) == set(CORPUS.makers)
    assert CORPUS.made_by_app


def test_each_hostile_file_is_what_it_says() -> None:
    assert len(CORPUS.hostile["zstd_bomb"]()) < 1 << 20
    assert CORPUS.hostile["after_the_end"]().endswith(b"#!/bin/sh\nid\n")
    assert CORPUS.hostile["pointer_size"]()[:12] == b"BLENDER_v405"
    made = sorted(path.stem for path in HOSTILE_FOLDER.glob("*.blend"))
    assert made == [
        "animation",
        "external_image",
        "library_link",
        "packed_image",
        "python_driver",
        "script_node",
        "simple_driver",
        "text_block",
    ]
    for name in made:
        assert read(CORPUS.hostile[name]()).data.startswith(HEADER), "Blender 5.2's own"
