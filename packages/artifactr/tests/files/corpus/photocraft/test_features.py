"""PhotoCraft's corpus: what each feature's value means."""

from tests.files.corpus.photocraft.corpus import CORPUS
from tests.files.corpus.photocraft.features import READERS, read, unpack


def value(feature: str) -> object:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("visibility_and_opacity") == [
        ("Hidden", False, 255),
        ("Half", True, 128),
        ("Background", True, 255),
    ]
    assert value("blend_modes") == [
        ("Multiply", "mul "),
        ("Screen", "scrn"),
        ("Background", "norm"),
    ]
    assert value("groups") == [(("Shapes",), "Inside"), ((), "Background")]
    assert value("resolution") == [(8, 6, 300, 300)]


def test_packbits_are_read_as_a_save_writes_them() -> None:
    """Two rows: a literal of two bytes, then a no-op and a run of four."""
    rle = b"\x00\x01" + b"\x00\x03\x00\x03" + b"\x01\x05\x06" + b"\x80\xfd\x09"
    assert unpack(rle, 2, 4) == b"\x05\x06" + b"\x09" * 4
    assert unpack(b"\x00\x00\x01\x02", 1, 2) == b"\x01\x02"


def test_every_feature_has_a_reader() -> None:
    assert set(READERS) == set(CORPUS.makers)


def test_each_hostile_file_is_its_format_broken() -> None:
    assert CORPUS.hostile_file("large")[4:6] == b"\x00\x02"
    assert CORPUS.hostile_file("vast")[14:18] == (300_000).to_bytes(4, "big")
    assert len(CORPUS.hostile_file("overrun")) < 1 << 30
