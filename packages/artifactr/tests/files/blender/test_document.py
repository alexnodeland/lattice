"""What the adapter reads of a Blender file before Blender starts: what it refuses, the file it
writes again, and its fingerprint."""

import struct

import pytest
import zstandard

from artifactr.files.app import AppFailed
from artifactr.files.blender import fingerprint, scan
from artifactr.files.blender.document import (
    HEAD,
    HEADER,
    RAW,
    STRUCTS,
    THUMBNAIL,
    read,
)
from tests.files.corpus.blender.corpus import CORPUS, HOSTILE, changed, first, plain, pointed

SOURCE = CORPUS.source("primitives")


def ended(data: bytearray, code: bytes, index: int, payload: bytes, count: int = 1) -> bytes:
    """A file with a block of its own before its `ENDB`."""
    end = len(data) - HEAD.size
    head = HEAD.pack(code, index, 0x1000, len(payload), count)
    return bytes(data[:end] + head + payload + data[end:])


def index_of(name: str) -> int:
    return read(SOURCE).catalogue.index(name)


def test_a_file_blender_saved_is_written_again_without_its_thumbnail() -> None:
    scanned = scan(SOURCE)
    assert scanned.compressed
    assert scanned.content.startswith(HEADER)
    blend = read(scanned.content)
    assert not blend.compressed
    assert THUMBNAIL in {block.code for block in read(SOURCE).blocks}
    assert THUMBNAIL not in {block.code for block in blend.blocks}
    assert scan(scanned.content).content == scanned.content, "uncompressed, as Blender is given"


@pytest.mark.parametrize("feature", sorted(CORPUS.makers))
def test_every_corpus_file_is_allowed_and_its_fingerprint_kept(feature: str) -> None:
    source = CORPUS.source(feature)
    assert fingerprint(scan(source).content) == fingerprint(source)


def test_a_fingerprint_leaves_out_what_each_save_stamps() -> None:
    def stamped(data: bytearray) -> None:
        _, at = first(data, "FileGlobal")
        offset, _ = read(bytes(data)).catalogue.field(index_of("FileGlobal"), b"filename")
        data[at + offset : at + offset + 9] = b"/tmp/call"

    assert fingerprint(changed("primitives", stamped)) == fingerprint(SOURCE)
    loc, _ = read(SOURCE).catalogue.field(index_of("Object"), b"loc")
    moved = changed(
        "primitives", lambda d: struct.pack_into("<f", d, first(d, "Object")[1] + loc, 9)
    )
    assert fingerprint(moved) != fingerprint(SOURCE), "an object's place is its own"


@pytest.mark.parametrize(
    ("name", "failure", "why"),
    [
        ("text_block", "refused", "a text, which may be a script"),
        ("python_driver", "refused", "animation or a driver, which may run Python: AnimData"),
        ("simple_driver", "refused", "animation or a driver, which may run Python: AnimData"),
        ("animation", "refused", "animation or a driver, which may run Python: AnimData"),
        ("confused_pointer", "refused", "Object.adt points at animation or a driver"),
        ("confused_parent", "refused", "Object.parent points at Camera, not Object"),
        ("confused_data", "refused", "an object of type 10 holds data of another type"),
        ("node_data_block", "refused", "bNode.id points at Object, not ID"),
        ("library_link", "refused", "a link to another file"),
        ("packed_image", "refused", "an image"),
        ("external_image", "refused", "an image"),
        ("script_node", "refused", "a script node"),
        ("zstd_bomb", "too_large", "inflates past"),
        ("gzip", "refused", "gzip"),
        ("pointer_size", "refused", "its header is b'BLENDER_v405"),
        ("big_endian", "refused", "its header is b'BLENDER-V405"),
        ("another_version", "refused", "its header is b'BLENDER17-01v0503'"),
        ("lying_length", "refused", "lies about its size"),
        ("negative_length", "refused", "lies about its size"),
        ("huge_count", "refused", "size isn't its count's"),
        ("no_struct", "refused", "struct 30000, which isn't one"),
        ("after_the_end", "refused", "bytes after its end"),
        ("another_catalogue", "refused", "isn't Blender 5.2's"),
    ],
)
def test_each_hostile_file_is_refused_before_blender_starts(
    name: str, failure: str, why: str
) -> None:
    with pytest.raises(AppFailed, match=why) as failed:
        scan(HOSTILE[name]())
    assert failed.value.failure == failure


def test_a_parents_cycle_is_left_to_the_script() -> None:
    """A parent is an object, which the scan allows: Blender reads it, and the script refuses."""
    assert scan(HOSTILE["cycle"]())


@pytest.mark.parametrize(
    ("content", "why"),
    [
        (b"", "not a Blender file"),
        (b"PK\x03\x04", "not a Blender file"),
        (b"\x28\xb5\x2f\xfd" + b"\xff" * 16, "its zstd doesn't inflate"),
        (bytes(plain("primitives"))[:-1], "ends before its last block"),
        (HEADER, "ends before its last block"),
    ],
)
def test_what_isnt_a_whole_blender_file_is_refused(content: bytes, why: str) -> None:
    with pytest.raises(AppFailed, match=why):
        scan(content)


def test_a_file_past_the_limit_is_too_large_compressed_or_not() -> None:
    for content in (SOURCE, bytes(plain("primitives"))):
        with pytest.raises(AppFailed, match=r"past|larger") as failed:
            scan(content, 1024)
        assert failed.value.failure == "too_large"


def test_a_file_of_too_many_blocks_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("artifactr.files.blender.document.BLOCKS", 100)
    with pytest.raises(AppFailed, match="more than 100 blocks"):
        scan(SOURCE)


def test_a_file_must_hold_one_catalogue() -> None:
    data = plain("primitives")
    blend = read(bytes(data))
    (dna,) = [block for block in blend.blocks if block.code == b"DNA1"]
    twice = ended(data, b"DNA1", 0, bytes(data[dna.bytes_start : dna.end]))
    with pytest.raises(AppFailed, match="one catalogue"):
        scan(twice)
    without = bytes(data[: dna.start] + data[dna.end :])
    with pytest.raises(AppFailed, match="one catalogue"):
        scan(without)


def test_a_data_block_outside_the_allowed_ones_is_refused() -> None:
    with pytest.raises(AppFailed, match=r"a data-block that isn't allowed: b'XX'"):
        scan(ended(plain("primitives"), b"XX\0\0", RAW, b""))
    with pytest.raises(AppFailed, match="a node group"):
        scan(ended(plain("primitives"), b"NT\0\0", RAW, b""))


def test_a_struct_outside_the_allowed_ones_is_refused() -> None:
    catalogue = read(SOURCE).catalogue
    for name, why in (("PackedFile", "a packed file"), ("Strip", "a struct that isn't allowed")):
        index = index_of(name)
        payload = bytes(catalogue.size(index))
        with pytest.raises(AppFailed, match=f"{why}: {name}"):
            scan(ended(plain("primitives"), b"DATA", index, payload))


def test_raw_data_is_allowed_but_a_script_nodes_name_in_it_isnt() -> None:
    assert scan(ended(plain("primitives"), b"DATA", RAW, b"any bytes at all"))
    with pytest.raises(AppFailed, match="a script node"):
        scan(ended(plain("primitives"), b"DATA", RAW, b"..ShaderNodeScript.."))


def test_a_pointer_at_a_struct_outside_the_allowed_ones_is_refused_with_why() -> None:
    with pytest.raises(AppFailed, match=r"Mesh\.key points at a struct that isn't allowed: Key"):
        scan(changed("primitives", pointed("Mesh", b"key", "Object")))


def test_a_pointer_at_raw_data_as_a_struct_is_refused() -> None:
    def at_raw(data: bytearray) -> None:
        blend = read(bytes(data))
        raw = next(b for b in blend.blocks if b.code == b"DATA" and b.index == RAW)
        offset, _ = blend.catalogue.field(index_of("Object"), b"parent")
        struct.pack_into("<Q", data, first(data, "Object")[1] + offset, raw.address)

    with pytest.raises(AppFailed, match=r"Object\.parent points at raw data, not Object"):
        scan(changed("primitives", at_raw))


def test_an_object_of_a_type_the_commands_dont_make_is_refused() -> None:
    def curve(data: bytearray) -> None:
        offset, _ = read(bytes(data)).catalogue.field(index_of("Object"), b"type")
        struct.pack_into("<h", data, first(data, "Object")[1] + offset, 2)

    with pytest.raises(AppFailed, match="an object of type 2, which isn't allowed"):
        scan(changed("primitives", curve))


def test_the_catalogue_is_read_as_blender_lays_its_structs_out() -> None:
    catalogue = read(SOURCE).catalogue
    for index in range(len(catalogue.structs)):
        assert sum(size for *_, size in catalogue.fields(index)) == catalogue.size(index)
    assert {"ID", "ModifierData", "SpaceLink"} <= catalogue.pointable
    assert catalogue.pointable >= STRUCTS
    assert catalogue.field(index_of("Object"), b"parent") == (496, 8)


def test_a_compressed_file_and_its_bytes_have_one_fingerprint() -> None:
    data = bytes(plain("primitives"))
    assert fingerprint(zstandard.ZstdCompressor().compress(data)) == fingerprint(data)
